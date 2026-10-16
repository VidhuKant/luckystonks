from __future__ import annotations

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command

from .codec import encode_admin_reset, encode_command, encode_config_change
from .leader_replicate import (
    init_leader_tracking,
    push_commit_to_followers,
    replicate_entry,
)
from .log_entry import LogEntry
from .node import RaftNode
from .peers import PeerRegistry


class InMemoryCluster:
    def __init__(self, peer_ids: list[int]) -> None:
        self.nodes: dict[int, RaftNode] = {
            pid: RaftNode(pid, Engine()) for pid in peer_ids
        }
        self.next_index: dict[int, int] = {}
        self.match_index: dict[int, int] = {}
        raft = {pid: f"127.0.0.1:{60051 + pid}" for pid in peer_ids}
        trading = {pid: f"127.0.0.1:{50051 + pid}" for pid in peer_ids}
        self.registry = PeerRegistry(peer_ids[0], raft, trading)
        for node in self.nodes.values():
            node.config_change_hooks.append(self._apply_config)

    def _apply_config(self, payload: dict[str, str | int]) -> None:
        self.registry.apply_config_change(payload)

    def seed_all(self) -> None:
        for node in self.nodes.values():
            node.engine.seed_demo_users()

    def _follower_ids(self, leader_id: int) -> list[int]:
        return [pid for pid in self.registry.peer_ids() if pid != leader_id]

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

    def _send_snapshot(
        self,
        leader_id: int,
        to_peer: int,
        term: int,
        last_included_index: int,
        last_included_term: int,
        data: bytes,
    ) -> dict[str, int | bool]:
        reply = self.nodes[to_peer].handle_install_snapshot(
            from_peer=leader_id,
            to_peer=to_peer,
            term=term,
            last_included_index=last_included_index,
            last_included_term=last_included_term,
            data=data,
        )
        return {"entry_appended": True, "match_index": last_included_index, "term": int(reply["term"])}

    def run_election(self, candidate_id: int) -> int | None:
        candidate = self.nodes[candidate_id]
        term = candidate.begin_election()
        votes = 1
        for pid in self.registry.peer_ids():
            if pid == candidate_id:
                continue
            node = self.nodes[pid]
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

        cluster_size = len(self.registry.peer_ids())
        if votes > cluster_size // 2:
            candidate.become_leader()
            for pid, node in self.nodes.items():
                if pid != candidate_id:
                    node.role = "follower"
            self.next_index, self.match_index = init_leader_tracking(
                candidate, self._follower_ids(candidate_id)
            )
            return candidate_id
        return None

    def _replicate(self, leader_id: int, entry: LogEntry) -> bool:
        leader = self.nodes[leader_id]
        if leader.role != "leader":
            return False
        followers = self._follower_ids(leader_id)
        if not self.next_index or any(pid not in self.next_index for pid in followers):
            self.next_index, self.match_index = init_leader_tracking(leader, followers)
        cluster_size = len(self.registry.peer_ids())

        def send(pid, term, prev_index, prev_term, commit, entries):
            return self._send_append(leader_id, pid, term, prev_index, prev_term, commit, entries)

        def send_snapshot(pid, term, last_included_index, last_included_term, data):
            return self._send_snapshot(
                leader_id, pid, term, last_included_index, last_included_term, data
            )

        ok = replicate_entry(
            leader,
            entry,
            followers,
            send,
            self.next_index,
            self.match_index,
            cluster_size,
            send_snapshot,
        )
        if ok:
            push_commit_to_followers(
                leader,
                followers,
                send,
                self.next_index,
                self.match_index,
                send_snapshot,
            )
        return ok

    def replicate_command(self, leader_id: int, command: Command) -> bool:
        leader = self.nodes[leader_id]
        entry = LogEntry(leader.current_term, encode_command(command))
        return self._replicate(leader_id, entry)

    def replicate_admin_reset(self, leader_id: int, seed_path: str) -> bool:
        leader = self.nodes[leader_id]
        entry = LogEntry(leader.current_term, encode_admin_reset(seed_path))
        return self._replicate(leader_id, entry)

    def replicate_config_change(
        self, leader_id: int, action: str, peer_id: int, raft_addr: str, trading_addr: str
    ) -> bool:
        leader = self.nodes[leader_id]
        entry = LogEntry(
            leader.current_term,
            encode_config_change(action, peer_id, raft_addr, trading_addr),
        )
        ok = self._replicate(leader_id, entry)
        if ok:
            self.next_index, self.match_index = init_leader_tracking(
                leader, self._follower_ids(leader_id)
            )
        if ok and action == "add" and peer_id not in self.nodes:
            self.nodes[peer_id] = RaftNode(peer_id, Engine())
            new_node = self.nodes[peer_id]
            new_node.config_change_hooks.append(self._apply_config)
            new_node.current_term = leader.current_term
            new_node.log = list(leader.log)
            new_node.commit_index = leader.commit_index
            new_node.last_applied = leader.last_applied
            new_node.snapshot_last_included_index = leader.snapshot_last_included_index
            new_node.snapshot_last_included_term = leader.snapshot_last_included_term
            new_node.snapshot_data = leader.snapshot_data
            new_node.engine.load_state_bytes(leader.engine.dump_state_bytes())
        if ok and action == "remove":
            self.nodes.pop(peer_id, None)
        return ok
