from __future__ import annotations

import logging
from collections.abc import Callable

from .log_entry import LogEntry
from .node import RaftNode

AppendReply = dict[str, int | bool]
SendAppend = Callable[[int, int, int, int, int, list[LogEntry]], AppendReply | None]


def init_leader_tracking(leader: RaftNode, follower_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    last = leader.last_log_index()
    next_index = {pid: last + 1 for pid in follower_ids}
    match_index = {pid: 0 for pid in follower_ids}
    return next_index, match_index


def _log_term(leader: RaftNode, index: int) -> int:
    if index <= 0:
        return 0
    if index > leader.last_log_index():
        return leader.last_log_term()
    return leader.log[index - 1].term


def advance_commit(
    leader: RaftNode,
    match_index: dict[int, int],
    follower_ids: list[int],
    log: logging.LoggerAdapter | None = None,
) -> None:
    old_commit = leader.commit_index
    quorum = len(follower_ids) + 1
    for index in range(leader.commit_index + 1, leader.last_log_index() + 1):
        if leader.log[index - 1].term != leader.current_term:
            continue
        replicated = 1
        for pid in follower_ids:
            if match_index.get(pid, 0) >= index:
                replicated += 1
        if replicated > quorum // 2:
            leader.commit_index = index
    if log is not None and leader.commit_index > old_commit:
        log.info("commit advanced to %s (was %s)", leader.commit_index, old_commit)
    leader._apply_committed(log=log)


def replicate_entry(
    leader: RaftNode,
    entry: LogEntry,
    follower_ids: list[int],
    send_append: SendAppend,
    next_index: dict[int, int],
    match_index: dict[int, int],
    log: logging.LoggerAdapter | None = None,
) -> bool:
    leader.log.append(entry)
    term = leader.current_term
    target_index = leader.last_log_index()

    for pid in follower_ids:
        while True:
            ni = next_index[pid]
            if ni > leader.last_log_index() + 1:
                next_index[pid] = leader.last_log_index() + 1
                ni = next_index[pid]
            prev_index = ni - 1
            prev_term = _log_term(leader, prev_index)
            entries = leader.log[ni - 1 :] if ni <= leader.last_log_index() else []
            reply = send_append(pid, term, prev_index, prev_term, leader.commit_index, entries)
            if reply is None:
                break
            reply_term = int(reply.get("term", term))
            if reply_term > term:
                leader.log.pop()
                return False
            if reply.get("entry_appended"):
                match_index[pid] = int(reply["match_index"])
                next_index[pid] = int(reply["match_index"]) + 1
                break
            old_ni = next_index[pid]
            next_index[pid] = max(1, next_index[pid] - 1)
            if log is not None and next_index[pid] < old_ni:
                log.debug(
                    "backtrack follower=%s nextIndex %s -> %s",
                    pid,
                    old_ni,
                    next_index[pid],
                )
            if next_index[pid] <= leader.commit_index and entries:
                leader.log.pop()
                return False
            if next_index[pid] == old_ni:
                break

    advance_commit(leader, match_index, follower_ids, log=log)
    return leader.commit_index >= target_index


def _sync_follower(
    leader: RaftNode,
    pid: int,
    term: int,
    commit: int,
    send_append: SendAppend,
    next_index: dict[int, int],
    match_index: dict[int, int],
) -> None:
    while True:
        ni = next_index.get(pid, leader.last_log_index() + 1)
        ni = min(max(1, ni), leader.last_log_index() + 1)
        prev_index = ni - 1
        if prev_index > leader.last_log_index():
            return
        prev_term = _log_term(leader, prev_index)
        entries = leader.log[ni - 1 :] if ni <= leader.last_log_index() else []
        reply = send_append(pid, term, prev_index, prev_term, commit, entries)
        if reply is None:
            return
        reply_term = int(reply.get("term", term))
        if reply_term > term:
            return
        if reply.get("entry_appended"):
            match_index[pid] = int(reply["match_index"])
            next_index[pid] = int(reply["match_index"]) + 1
            if entries:
                continue
            return
        old_ni = next_index[pid]
        next_index[pid] = max(1, next_index[pid] - 1)
        if next_index[pid] == old_ni:
            return


def push_commit_to_followers(
    leader: RaftNode,
    follower_ids: list[int],
    send_append: SendAppend,
    next_index: dict[int, int],
    match_index: dict[int, int],
    log: logging.LoggerAdapter | None = None,
) -> None:
    term = leader.current_term
    commit = leader.commit_index
    for pid in follower_ids:
        _sync_follower(leader, pid, term, commit, send_append, next_index, match_index)
