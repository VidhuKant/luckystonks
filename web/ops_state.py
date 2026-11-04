"""Cluster observability: health, leader inference, log tailing, Raft paper metrics."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from luckystonks.cluster_size import BASE_TRADING_PORT, cluster_size, peer_ids, raft_port, trading_port

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
    raft: dict[str, Any]


def default_peers(host: str = "127.0.0.1", size: int | None = None) -> list[dict[str, Any]]:
    n = cluster_size() if size is None else size
    return [
        {
            "peer_id": i,
            "trading_port": trading_port(i),
            "raft_port": raft_port(i),
            "host": host,
        }
        for i in peer_ids(n)
    ]


def load_pid_map(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    try:
        return {str(k): int(v) for k, v in json.loads(path.read_text()).items()}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def read_raft_meta(root: Path, peer_id: int) -> dict[str, Any]:
    """Merge persisted Raft state + live status export (paper field names)."""
    raft_path = root / "data" / "runtime" / f"raft-peer{peer_id}.json"
    status_path = root / "data" / "runtime" / f"raft-status-peer{peer_id}.json"
    meta: dict[str, Any] = {
        "currentTerm": None,
        "votedFor": None,
        "commitIndex": None,
        "lastApplied": None,
        "lastLogIndex": None,
        "lastLogTerm": None,
        "logLen": None,
        "snapshotLastIncludedIndex": 0,
        "snapshotLastIncludedTerm": 0,
        "nextIndex": None,
        "matchIndex": None,
        "role": None,
        "knownLeaderId": None,
        "clusterSize": None,
    }

    if raft_path.is_file():
        try:
            payload = json.loads(raft_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        if payload:
            snap = payload.get("snapshot") or {}
            log_rows = payload.get("log") or []
            snap_idx = int(snap.get("last_included_index", 0)) if snap else 0
            snap_term = int(snap.get("last_included_term", 0)) if snap else 0
            log_len = len(log_rows)
            last_log_index = snap_idx + log_len
            if log_rows:
                last_log_term = int(log_rows[-1].get("term", 0))
            else:
                last_log_term = snap_term
            meta.update(
                {
                    "currentTerm": int(payload.get("current_term", 0)),
                    "votedFor": payload.get("voted_for"),
                    "commitIndex": int(payload.get("commit_index", 0)),
                    "lastApplied": int(payload.get("last_applied", 0)),
                    "lastLogIndex": last_log_index,
                    "lastLogTerm": last_log_term,
                    "logLen": log_len,
                    "snapshotLastIncludedIndex": snap_idx,
                    "snapshotLastIncludedTerm": snap_term,
                }
            )

    if status_path.is_file():
        try:
            live = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            live = {}
        if live:
            for key in (
                "currentTerm",
                "votedFor",
                "commitIndex",
                "lastApplied",
                "lastLogIndex",
                "lastLogTerm",
                "logLen",
                "snapshotLastIncludedIndex",
                "snapshotLastIncludedTerm",
                "nextIndex",
                "matchIndex",
                "role",
                "knownLeaderId",
                "clusterSize",
                "electionTimeoutMin",
                "electionTimeoutMax",
                "electionTimeoutSec",
                "electionRemainingSec",
                "electionDeadlineAt",
                "heartbeatIntervalSec",
                "heartbeatRemainingSec",
                "heartbeatDeadlineAt",
            ):
                if key in live and live[key] is not None:
                    meta[key] = live[key]

    # Backward-compatible aliases used by older UI bits
    meta["term"] = meta["currentTerm"]
    meta["commit_index"] = meta["commitIndex"]
    meta["log_len"] = meta["logLen"]
    meta["snapshot_index"] = meta["snapshotLastIncludedIndex"]
    return meta


def infer_leader_from_logs(
    log_dir: Path,
    peer_id_list: list[int],
    alive_peer_ids: set[int] | None = None,
) -> int | None:
    """Pick the peer with the most recent 'became leader' log line among alive peers."""
    best_peer: int | None = None
    best_key = (-1.0, -1)
    for pid in peer_id_list:
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


def _pick_canonical_leader(
    alive_metas: list[tuple[int, dict[str, Any]]],
    log_leader_id: int | None,
) -> int | None:
    """Pick at most one display leader. Prefer live role=leader with nextIndex (Fig. 2)."""
    claiming: list[tuple[int, int, bool, bool]] = []
    for pid, meta in alive_metas:
        live_role = str(meta.get("role") or "").lower()
        if live_role != "leader":
            continue
        term = int(meta.get("currentTerm") or 0)
        has_tracking = isinstance(meta.get("nextIndex"), dict)
        matches_log = log_leader_id is not None and pid == log_leader_id
        claiming.append((term, pid, has_tracking, matches_log))
    if claiming:
        claiming.sort(key=lambda row: (row[0], row[2], row[3], -row[1]), reverse=True)
        return claiming[0][1]
    return log_leader_id


def build_cluster_status(
    *,
    root: Path,
    log_dir: Path,
    pid_file: Path,
    host: str,
    probe_trading,
    probe_raft,
) -> dict[str, Any]:
    size = cluster_size()
    peers_cfg = default_peers(host, size)
    pids = load_pid_map(pid_file)
    ids = [p["peer_id"] for p in peers_cfg]
    peers: list[dict[str, Any]] = []
    alive: set[int] = set()
    rows: list[tuple[dict[str, Any], dict[str, Any], bool, bool, str]] = []

    # Probe all peers in parallel so two DOWN nodes don't serialize ~3s of timeouts.
    probe_results: dict[int, tuple[bool, bool]] = {}

    def _probe_one(p: dict[str, Any]) -> tuple[int, bool, bool]:
        pid = int(p["peer_id"])
        return pid, bool(probe_trading(host, p["trading_port"])), bool(probe_raft(host, p["raft_port"]))

    workers = max(1, min(len(peers_cfg), 8))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_probe_one, p) for p in peers_cfg]
        for fut in as_completed(futs):
            pid, trading_up, raft_up = fut.result()
            probe_results[pid] = (trading_up, raft_up)

    for p in peers_cfg:
        pid = int(p["peer_id"])
        trading_up, raft_up = probe_results.get(pid, (False, False))
        if trading_up:
            alive.add(pid)
        meta = read_raft_meta(root, pid)
        log_path = log_dir / f"peer{pid}.log"
        last_line = ""
        if log_path.is_file():
            try:
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                last_line = lines[-1] if lines else ""
            except OSError:
                pass
        rows.append((p, meta, trading_up, raft_up, last_line))

    log_leader_id = infer_leader_from_logs(log_dir, ids, alive_peer_ids=alive or None)
    alive_metas = [
        (int(p["peer_id"]), meta)
        for p, meta, trading_up, raft_up, _ in rows
        if trading_up and raft_up
    ]
    leader_id = _pick_canonical_leader(alive_metas, log_leader_id)

    for p, meta, trading_up, raft_up, last_line in rows:
        pid = int(p["peer_id"])
        live_role = str(meta.get("role") or "").lower()
        role = "DOWN"
        if trading_up and raft_up:
            if leader_id is not None and pid == leader_id:
                role = "LEADER"
            elif live_role == "candidate":
                role = "CANDIDATE"
            elif live_role in ("follower", "leader"):
                # Stale self-reported "leader" from another peer → show FOLLOWER
                role = "FOLLOWER"
            elif leader_id is not None:
                role = "FOLLOWER"
            else:
                role = "UNKNOWN"

        raft_fields = {
            "currentTerm": meta.get("currentTerm"),
            "votedFor": meta.get("votedFor"),
            "commitIndex": meta.get("commitIndex"),
            "lastApplied": meta.get("lastApplied"),
            "lastLogIndex": meta.get("lastLogIndex"),
            "lastLogTerm": meta.get("lastLogTerm"),
            "logLen": meta.get("logLen"),
            "snapshotLastIncludedIndex": meta.get("snapshotLastIncludedIndex"),
            "snapshotLastIncludedTerm": meta.get("snapshotLastIncludedTerm"),
            "nextIndex": meta.get("nextIndex") if role == "LEADER" else None,
            "matchIndex": meta.get("matchIndex") if role == "LEADER" else None,
            "knownLeaderId": meta.get("knownLeaderId"),
            "electionTimeoutMin": meta.get("electionTimeoutMin"),
            "electionTimeoutMax": meta.get("electionTimeoutMax"),
            "electionTimeoutSec": meta.get("electionTimeoutSec"),
            "electionRemainingSec": meta.get("electionRemainingSec"),
            "electionDeadlineAt": meta.get("electionDeadlineAt"),
            "heartbeatIntervalSec": meta.get("heartbeatIntervalSec"),
            "heartbeatRemainingSec": meta.get("heartbeatRemainingSec"),
            "heartbeatDeadlineAt": meta.get("heartbeatDeadlineAt"),
        }
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
            raft=raft_fields,
        )
        peers.append(asdict(status))

    client_port = int(os.environ.get("UI_CLIENT_TRADING_PORT", str(BASE_TRADING_PORT + 1)))

    return {
        "cluster_size": size,
        "quorum": size // 2 + 1,
        "leader_peer_id": leader_id,
        "client_trading_port": client_port,
        "peers": peers,
        "ts": time.time(),
    }


def classify_log_line(line: str) -> str:
    return "election" if ELECTION_PATTERNS.search(line) else "general"
