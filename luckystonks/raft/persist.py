from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING

from .log_entry import LogEntry

if TYPE_CHECKING:
    from .node import RaftNode


def save_raft_state(path: str | Path, node: RaftNode) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
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
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_raft_state(path: str | Path, node: "RaftNode") -> None:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
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
