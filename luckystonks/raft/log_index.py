from __future__ import annotations

from typing import TYPE_CHECKING

from .log_entry import LogEntry

if TYPE_CHECKING:
    from .node import RaftNode


def last_log_index(node: RaftNode) -> int:
    return node.snapshot_last_included_index + len(node.log)


def last_log_term(node: RaftNode) -> int:
    if node.log:
        return node.log[-1].term
    return node.snapshot_last_included_term


def term_at(node: RaftNode, index: int) -> int:
    if index == 0:
        return 0
    if index == node.snapshot_last_included_index:
        return node.snapshot_last_included_term
    if index < node.snapshot_last_included_index:
        return 0
    local = index - node.snapshot_last_included_index
    if local > len(node.log):
        return last_log_term(node)
    return node.log[local - 1].term


def entry_at(node: RaftNode, index: int) -> LogEntry | None:
    if index <= node.snapshot_last_included_index:
        return None
    local = index - node.snapshot_last_included_index
    if local < 1 or local > len(node.log):
        return None
    return node.log[local - 1]
