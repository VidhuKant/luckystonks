from __future__ import annotations

import logging
from collections.abc import Callable

from . import log_index
from .log_entry import LogEntry
from .node import RaftNode

AppendReply = dict[str, int | bool]
SendAppend = Callable[[int, int, int, int, int, list[LogEntry]], AppendReply | None]
SendSnapshot = Callable[[int, int, int, int, bytes], AppendReply | None]


def init_leader_tracking(leader: RaftNode, follower_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    last = leader.last_log_index()
    next_index = {pid: last + 1 for pid in follower_ids}
    match_index = {pid: 0 for pid in follower_ids}
    return next_index, match_index


def _try_send_snapshot(
    leader: RaftNode,
    pid: int,
    term: int,
    send_snapshot: SendSnapshot | None,
    next_index: dict[int, int],
    match_index: dict[int, int],
    log: logging.LoggerAdapter | None,
) -> bool:
    if send_snapshot is None:
        return False
    if not leader.snapshot_data or leader.snapshot_last_included_index <= 0:
        return False
    if next_index.get(pid, 1) > leader.snapshot_last_included_index:
        return False
    reply = send_snapshot(
        pid,
        term,
        leader.snapshot_last_included_index,
        leader.snapshot_last_included_term,
        leader.snapshot_data,
    )
    if reply is None:
        return False
    if int(reply.get("term", term)) > term:
        return False
    match_index[pid] = leader.snapshot_last_included_index
    next_index[pid] = leader.snapshot_last_included_index + 1
    if log is not None:
        log.info(
            "sent snapshot to follower=%s through_index=%s",
            pid,
            leader.snapshot_last_included_index,
        )
    return True


def advance_commit(
    leader: RaftNode,
    match_index: dict[int, int],
    follower_ids: list[int],
    cluster_size: int,
    log: logging.LoggerAdapter | None = None,
) -> None:
    old_commit = leader.commit_index
    quorum = cluster_size
    for index in range(leader.commit_index + 1, leader.last_log_index() + 1):
        if log_index.term_at(leader, index) != leader.current_term:
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
    cluster_size: int,
    send_snapshot: SendSnapshot | None = None,
    log: logging.LoggerAdapter | None = None,
) -> bool:
    leader.log.append(entry)
    term = leader.current_term
    target_index = leader.last_log_index()

    for pid in follower_ids:
        while True:
            if _try_send_snapshot(leader, pid, term, send_snapshot, next_index, match_index, log):
                continue
            ni = next_index[pid]
            if ni > leader.last_log_index() + 1:
                next_index[pid] = leader.last_log_index() + 1
                ni = next_index[pid]
            prev_index = ni - 1
            prev_term = log_index.term_at(leader, prev_index)
            entries = (
                leader.log[ni - leader.snapshot_last_included_index - 1 :]
                if ni <= leader.last_log_index()
                else []
            )
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
            if prev_index <= leader.snapshot_last_included_index:
                if not _try_send_snapshot(leader, pid, term, send_snapshot, next_index, match_index, log):
                    break
                continue
            next_index[pid] = max(leader.snapshot_last_included_index + 1, next_index[pid] - 1)
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

    advance_commit(leader, match_index, follower_ids, cluster_size, log=log)
    return leader.commit_index >= target_index


def _sync_follower(
    leader: RaftNode,
    pid: int,
    term: int,
    commit: int,
    send_append: SendAppend,
    next_index: dict[int, int],
    match_index: dict[int, int],
    send_snapshot: SendSnapshot | None = None,
    log: logging.LoggerAdapter | None = None,
) -> None:
    while True:
        if _try_send_snapshot(leader, pid, term, send_snapshot, next_index, match_index, log):
            continue
        ni = next_index.get(pid, leader.last_log_index() + 1)
        ni = min(max(leader.snapshot_last_included_index + 1, ni), leader.last_log_index() + 1)
        prev_index = ni - 1
        if prev_index > leader.last_log_index():
            return
        prev_term = log_index.term_at(leader, prev_index)
        entries = (
            leader.log[ni - leader.snapshot_last_included_index - 1 :]
            if ni <= leader.last_log_index()
            else []
        )
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
        if prev_index <= leader.snapshot_last_included_index:
            if _try_send_snapshot(leader, pid, term, send_snapshot, next_index, match_index, log):
                continue
            return
        next_index[pid] = max(leader.snapshot_last_included_index + 1, next_index[pid] - 1)
        if next_index[pid] == old_ni:
            return


def push_commit_to_followers(
    leader: RaftNode,
    follower_ids: list[int],
    send_append: SendAppend,
    next_index: dict[int, int],
    match_index: dict[int, int],
    send_snapshot: SendSnapshot | None = None,
    log: logging.LoggerAdapter | None = None,
) -> None:
    term = leader.current_term
    commit = leader.commit_index
    for pid in follower_ids:
        _sync_follower(
            leader,
            pid,
            term,
            commit,
            send_append,
            next_index,
            match_index,
            send_snapshot,
            log,
        )
