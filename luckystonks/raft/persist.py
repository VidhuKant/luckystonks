from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING

from .cluster_config import PeerEndpoint
from .log_entry import LogEntry

if TYPE_CHECKING:
    from .node import RaftNode


def save_raft_state(path: str | Path, node: RaftNode) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_block = None
    if node.snapshot_data and node.snapshot_last_included_index > 0:
        snapshot_block = {
            "last_included_index": node.snapshot_last_included_index,
            "last_included_term": node.snapshot_last_included_term,
            "data": base64.b64encode(node.snapshot_data).decode("ascii"),
        }
    payload = {
        "version": 2,
        "current_term": node.current_term,
        "voted_for": node.voted_for,
        "commit_index": node.commit_index,
        "last_applied": node.last_applied,
        "log": [
            {
                "term": entry.term,
                "command": base64.b64encode(entry.command).decode("ascii"),
            }
            for entry in node.log
        ],
        "snapshot": snapshot_block,
        "cluster": [ep.to_dict() for ep in node.cluster_endpoints],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_raft_state(path: str | Path, node: "RaftNode") -> None:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version", 1)
    if version not in (1, 2):
        raise ValueError("unsupported raft state version")
    node.current_term = int(payload["current_term"])
    voted = payload.get("voted_for")
    node.voted_for = int(voted) if voted is not None else None
    node.commit_index = int(payload["commit_index"])
    node.last_applied = int(payload["last_applied"])
    node.log = [
        LogEntry(int(row["term"]), base64.b64decode(row["command"]))
        for row in payload.get("log", [])
    ]
    node.snapshot_last_included_index = 0
    node.snapshot_last_included_term = 0
    node.snapshot_data = None
    snap = payload.get("snapshot")
    if snap:
        node.snapshot_last_included_index = int(snap["last_included_index"])
        node.snapshot_last_included_term = int(snap["last_included_term"])
        node.snapshot_data = base64.b64decode(snap["data"])
        if node.last_applied < node.snapshot_last_included_index:
            node.last_applied = node.snapshot_last_included_index
    if version >= 2:
        node.cluster_endpoints = [PeerEndpoint.from_dict(row) for row in payload.get("cluster", [])]
    if node.snapshot_data and node.last_applied >= node.snapshot_last_included_index:
        node.engine.load_state_bytes(node.snapshot_data)
