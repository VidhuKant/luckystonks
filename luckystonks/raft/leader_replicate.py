from __future__ import annotations

from collections.abc import Callable

from .log_entry import LogEntry
from .node import RaftNode

AppendReply = dict[str, int | bool]
SendAppend = Callable[[int, int, int, int, int, list[LogEntry]], AppendReply]


def init_leader_tracking(leader: RaftNode, follower_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    last = leader.last_log_index()
    next_index = {pid: last + 1 for pid in follower_ids}
    match_index = {pid: 0 for pid in follower_ids}
    return next_index, match_index


def _log_term(leader: RaftNode, index: int) -> int:
    if index <= 0:
        return 0
    return leader.log[index - 1].term


def advance_commit(leader: RaftNode, match_index: dict[int, int], follower_ids: list[int]) -> None:
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
    leader._apply_committed()


def replicate_entry(
    leader: RaftNode,
    entry: LogEntry,
    follower_ids: list[int],
    send_append: SendAppend,
    next_index: dict[int, int],
    match_index: dict[int, int],
) -> bool:
    leader.log.append(entry)
    term = leader.current_term

    for pid in follower_ids:
        while True:
            ni = next_index[pid]
            prev_index = ni - 1
            prev_term = _log_term(leader, prev_index)
            entries = leader.log[ni - 1 :] if ni <= leader.last_log_index() else []
            reply = send_append(pid, term, prev_index, prev_term, leader.commit_index, entries)
            if reply.get("entry_appended"):
                match_index[pid] = int(reply["match_index"])
                next_index[pid] = int(reply["match_index"]) + 1
                break
            next_index[pid] = max(1, next_index[pid] - 1)
            if next_index[pid] <= leader.commit_index and entries:
                leader.log.pop()
                return False

    advance_commit(leader, match_index, follower_ids)
    return leader.commit_index >= leader.last_log_index()


def push_commit_to_followers(
    leader: RaftNode,
    follower_ids: list[int],
    send_append: SendAppend,
    next_index: dict[int, int],
    match_index: dict[int, int],
) -> None:
    term = leader.current_term
    commit = leader.commit_index
    for pid in follower_ids:
        ni = next_index.get(pid, leader.last_log_index() + 1)
        prev_index = ni - 1
        prev_term = _log_term(leader, prev_index)
        send_append(pid, term, prev_index, prev_term, commit, [])
