from __future__ import annotations

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command

from .codec import encode_admin_reset, encode_command
from .log_entry import LogEntry
from .node import RaftNode


class InMemoryCluster:
    def __init__(self, peer_ids: list[int]) -> None:
        self.nodes: dict[int, RaftNode] = {
            pid: RaftNode(pid, Engine()) for pid in peer_ids
        }

    def seed_all(self) -> None:
        for node in self.nodes.values():
            node.engine.seed_demo_users()

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
            return candidate_id
        return None

    def replicate_command(self, leader_id: int, command: Command) -> bool:
        leader = self.nodes[leader_id]
        if leader.role != "leader":
            return False

        term = leader.current_term
        prev_index = leader.last_log_index()
        prev_term = leader.last_log_term()
        entry = LogEntry(term, encode_command(command))
        new_index = prev_index + 1
        leader.log.append(entry)

        successes = 1
        for pid, node in self.nodes.items():
            if pid == leader_id:
                continue
            reply = node.handle_append_entries(
                from_peer=leader_id,
                to_peer=pid,
                term=term,
                prev_index=prev_index,
                prev_term=prev_term,
                leader_commit=0,
                entries=[entry],
            )
            if reply["entry_appended"]:
                successes += 1

        if successes <= len(self.nodes) // 2:
            return False

        for node in self.nodes.values():
            node.commit_index = new_index
            node._apply_committed()
        return True

    def replicate_admin_reset(self, leader_id: int, seed_path: str) -> bool:
        leader = self.nodes[leader_id]
        if leader.role != "leader":
            return False

        term = leader.current_term
        prev_index = leader.last_log_index()
        prev_term = leader.last_log_term()
        entry = LogEntry(term, encode_admin_reset(seed_path))
        new_index = prev_index + 1
        leader.log.append(entry)

        successes = 1
        for pid, node in self.nodes.items():
            if pid == leader_id:
                continue
            reply = node.handle_append_entries(
                from_peer=leader_id,
                to_peer=pid,
                term=term,
                prev_index=prev_index,
                prev_term=prev_term,
                leader_commit=0,
                entries=[entry],
            )
            if reply["entry_appended"]:
                successes += 1

        if successes <= len(self.nodes) // 2:
            leader.log.pop()
            return False

        for node in self.nodes.values():
            node.commit_index = new_index
            node._apply_committed()
        return True