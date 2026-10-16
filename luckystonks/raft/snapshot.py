from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from luckystonks.matching.engine import Engine

from . import log_index

if TYPE_CHECKING:
    from .node import RaftNode

DEFAULT_COMPACT_THRESHOLD = 8


def dump_engine_state(engine: Engine) -> bytes:
    return engine.dump_state_bytes()


def install_engine_state(engine: Engine, data: bytes) -> None:
    engine.load_state_bytes(data)


def compact_through_applied(node: RaftNode, log: logging.LoggerAdapter | None = None) -> bool:
    """Snapshot state through last_applied and discard compacted log prefix."""
    if node.last_applied <= node.snapshot_last_included_index:
        return False
    snap_index = node.last_applied
    snap_term = log_index.term_at(node, snap_index)
    old_base = node.snapshot_last_included_index
    node.snapshot_data = dump_engine_state(node.engine)
    node.snapshot_last_included_index = snap_index
    node.snapshot_last_included_term = snap_term
    node.log = node.log[snap_index - old_base :]
    if log is not None:
        log.info(
            "log compacted snapshot_through=%s retained_log=%s",
            snap_index,
            len(node.log),
        )
    node._maybe_persist()
    return True


def maybe_compact(node: RaftNode, threshold: int, log: logging.LoggerAdapter | None = None) -> None:
    if len(node.log) < threshold:
        return
    compact_through_applied(node, log=log)


def handle_install_snapshot(
    node: RaftNode,
    *,
    from_peer: int,
    term: int,
    last_included_index: int,
    last_included_term: int,
    data: bytes,
    log: logging.LoggerAdapter | None = None,
) -> dict[str, int]:
    if term < node.current_term:
        return _snapshot_reply(node, from_peer)

    if term > node.current_term:
        node.current_term = term
        node.voted_for = None
        node.role = "follower"

    if last_included_index <= node.snapshot_last_included_index:
        return _snapshot_reply(node, from_peer)

    install_engine_state(node.engine, data)
    node.snapshot_last_included_index = last_included_index
    node.snapshot_last_included_term = last_included_term
    node.snapshot_data = data
    node.log.clear()
    node.last_applied = last_included_index
    if last_included_index > node.commit_index:
        node.commit_index = last_included_index
    node._maybe_persist()
    if log is not None:
        log.info(
            "installed snapshot through=%s term=%s from leader=%s",
            last_included_index,
            last_included_term,
            from_peer,
        )
    return _snapshot_reply(node, from_peer)


def _snapshot_reply(node: RaftNode, to_peer: int) -> dict[str, int]:
    return {"from": node.peer_id, "to": to_peer, "term": node.current_term}
