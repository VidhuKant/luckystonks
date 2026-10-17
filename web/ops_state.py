"""Cluster observability: health, leader inference, log tailing."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ELECTION_PATTERNS = re.compile(
    r"(election started|became leader|election failed|stepping down|vote rpc|InstallSnapshot|installed snapshot|log compacted)",
    re.IGNORECASE,
)


@dataclass
class PeerStatus:
    peer_id: int
    trading_host: str
    trading_port: int
    raft_port: int
    trading_up: bool
    raft_up: bool
    role: str
    term: int | None
    commit_index: int | None
    log_len: int | None
    snapshot_index: int | None
    last_log_line: str
    pid: int | None


def default_peers(host: str = "127.0.0.1") -> list[dict[str, Any]]:
    return [
        {"peer_id": i, "trading_port": 50051 + i, "raft_port": 60051 + i, "host": host}
        for i in range(3)
    ]


def load_pid_map(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    try:
        return {str(k): int(v) for k, v in json.loads(path.read_text()).items()}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def read_raft_meta(raft_state_path: Path) -> dict[str, Any]:
    if not raft_state_path.is_file():
        return {}
    try:
        payload = json.loads(raft_state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    snap = payload.get("snapshot") or {}
    return {
        "term": int(payload.get("current_term", 0)),
        "commit_index": int(payload.get("commit_index", 0)),
        "log_len": len(payload.get("log", [])),
        "snapshot_index": int(snap.get("last_included_index", 0)) if snap else 0,
    }


def infer_leader_from_logs(
    log_dir: Path,
    peer_ids: list[int],
    alive_peer_ids: set[int] | None = None,
) -> int | None:
    """Pick the peer with the most recent 'became leader' log line among alive peers."""
    best_peer: int | None = None
    best_key = (-1.0, -1)
    for pid in peer_ids:
        if alive_peer_ids is not None and pid not in alive_peer_ids:
            continue
        log_file = log_dir / f"peer{pid}.log"
        if not log_file.is_file():
            continue
        try:
            mtime = log_file.stat().st_mtime
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(reversed(lines[-400:])):
            if "became leader" not in line:
                continue
            m = re.match(r"^(\d{2}:\d{2}:\d{2})", line)
            ts = _hhmmss_to_sortable(m.group(1)) if m else mtime
            key = (mtime + ts / 100000.0, len(lines) - idx)
            if key > best_key:
                best_key = key
                best_peer = pid
            break
    return best_peer


def _hhmmss_to_sortable(hhmmss: str) -> float:
    parts = hhmmss.split(":")
    if len(parts) != 3:
        return 0.0
    h, m, s = (int(p) for p in parts)
    return h * 3600 + m * 60 + s


def tail_log_file(path: Path, max_lines: int = 400) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict[str, str]] = []
    for line in lines[-max_lines:]:
        kind = "election" if ELECTION_PATTERNS.search(line) else "general"
        out.append({"line": line, "kind": kind})
    return out


def build_cluster_status(
    *,
    root: Path,
    log_dir: Path,
    pid_file: Path,
    host: str,
    probe_trading,
    probe_raft,
) -> dict[str, Any]:
    peers_cfg = default_peers(host)
    pids = load_pid_map(pid_file)
    peer_ids = [p["peer_id"] for p in peers_cfg]
    peers: list[dict[str, Any]] = []
    alive: set[int] = set()
    for p in peers_cfg:
        pid = p["peer_id"]
        if probe_trading(host, p["trading_port"]):
            alive.add(pid)
    leader_id = infer_leader_from_logs(log_dir, peer_ids, alive_peer_ids=alive or None)

    for p in peers_cfg:
        pid = p["peer_id"]
        trading_up = probe_trading(host, p["trading_port"])
        raft_up = probe_raft(host, p["raft_port"])
        meta = read_raft_meta(root / "data" / "runtime" / f"raft-peer{pid}.json")
        log_path = log_dir / f"peer{pid}.log"
        last_line = ""
        if log_path.is_file():
            try:
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                last_line = lines[-1] if lines else ""
            except OSError:
                pass
        role = "DOWN"
        if trading_up and raft_up:
            if leader_id == pid:
                role = "LEADER"
            elif leader_id is not None:
                role = "FOLLOWER"
            else:
                role = "UNKNOWN"
        status = PeerStatus(
            peer_id=pid,
            trading_host=host,
            trading_port=p["trading_port"],
            raft_port=p["raft_port"],
            trading_up=trading_up,
            raft_up=raft_up,
            role=role,
            term=meta.get("term"),
            commit_index=meta.get("commit_index"),
            log_len=meta.get("log_len"),
            snapshot_index=meta.get("snapshot_index"),
            last_log_line=last_line,
            pid=pids.get(str(pid)),
        )
        peers.append(asdict(status))

    client_port = int(__import__("os").environ.get("UI_CLIENT_TRADING_PORT", "50052"))

    return {
        "leader_peer_id": leader_id,
        "client_trading_port": client_port,
        "peers": peers,
        "ts": time.time(),
    }


def classify_log_line(line: str) -> str:
    return "election" if ELECTION_PATTERNS.search(line) else "general"
