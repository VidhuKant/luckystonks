from __future__ import annotations

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command

from .codec import encode_admin_reset, encode_command
from .leader_replicate import (
    init_leader_tracking,
    push_commit_to_followers,
    replicate_entry,
)
from .log_entry import LogEntry
from .node import RaftNode


class InMemoryCluster:
    def __init__(self, peer_ids: list[int]) -> None:
        self.nodes: dict[int, RaftNode] = {
            pid: RaftNode(pid, Engine()) for pid in peer_ids
        }
        self.next_index: dict[int, int] = {}
        self.match_index: dict[int, int] = {}

    def seed_all(self) -> None:
        for node in self.nodes.values():
            node.engine.seed_demo_users()

    def _follower_ids(self, leader_id: int) -> list[int]:
        return [pid for pid in self.nodes if pid != leader_id]

    def _send_append(
        self, leader_id: int, to_peer: int, term: int, prev_index: int, prev_term: int, commit: int, entries: list[LogEntry]
    ) -> dict[str, int | bool]:
        return self.nodes[to_peer].handle_append_entries(
            from_peer=leader_id,
            to_peer=to_peer,
            term=term,
            prev_index=prev_index,
            prev_term=prev_term,
            leader_commit=commit,
            entries=entries,
        )

    def run_election(self, candidate_id: int) -> int | None:
        candidate = self.nodes[candidate_id]
        term = candidate.begin_election()
        votes = 1
        for pid, node in self.nodes.items():
            if pid == candidate_id:
                continue
            reply = node.handle_request_vote(
                from_peer=candidate_id,
                to_peer=pid,
                term=term,
                last_log_index=candidate.last_log_index(),
                last_log_term=candidate.last_log_term(),
            )
            if int(reply["term"]) > term:
                candidate.current_term = int(reply["term"])
                candidate.role = "follower"
                candidate.voted_for = None
                return None
            if reply["vote_granted"]:
                votes += 1

        if votes > len(self.nodes) // 2:
            candidate.become_leader()
            for pid, node in self.nodes.items():
                if pid != candidate_id:
                    node.role = "follower"
            self.next_index, self.match_index = init_leader_tracking(
                candidate, self._follower_ids(candidate_id)
            )
            return candidate_id
        return None

    def replicate_command(self, leader_id: int, command: Command) -> bool:
        leader = self.nodes[leader_id]
        if leader.role != "leader":
            return False
        entry = LogEntry(leader.current_term, encode_command(command))
        followers = self._follower_ids(leader_id)

        def send(pid, term, prev_index, prev_term, commit, entries):
            return self._send_append(leader_id, pid, term, prev_index, prev_term, commit, entries)

        ok = replicate_entry(leader, entry, followers, send, self.next_index, self.match_index)
        if ok:
            push_commit_to_followers(leader, followers, send, self.next_index, self.match_index)
        return ok

    def replicate_admin_reset(self, leader_id: int, seed_path: str) -> bool:
        leader = self.nodes[leader_id]
        if leader.role != "leader":
            return False
        entry = LogEntry(leader.current_term, encode_admin_reset(seed_path))
        followers = self._follower_ids(leader_id)

        def send(pid, term, prev_index, prev_term, commit, entries):
            return self._send_append(leader_id, pid, term, prev_index, prev_term, commit, entries)

        ok = replicate_entry(leader, entry, followers, send, self.next_index, self.match_index)
        if ok:
            push_commit_to_followers(leader, followers, send, self.next_index, self.match_index)
        return ok
