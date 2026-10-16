from __future__ import annotations

import random
import threading
import time
from typing import TYPE_CHECKING

import grpc

from luckystonks.matching.models import Command
from luckystonks.pb import raft_pb2

from .codec import encode_admin_reset, encode_command
from .leader_replicate import (
    init_leader_tracking,
    push_commit_to_followers,
    replicate_entry,
)
from .log_entry import LogEntry
from .peers import PeerRegistry

if TYPE_CHECKING:
    from .node import RaftNode


class RaftRuntime:
    def __init__(self, node: RaftNode, peers: PeerRegistry) -> None:
        self.node = node
        self.peers = peers
        self.lock = threading.Lock()
        self.running = False
        self._thread: threading.Thread | None = None
        self.election_deadline = 0.0
        self.last_heartbeat_sent = 0.0
        self.heartbeat_interval = 0.1
        self.election_timeout_bounds = (0.25, 0.5)
        self.known_leader_id: int | None = None
        self.next_index: dict[int, int] = {}
        self.match_index: dict[int, int] = {}

    def reset_election_timer(self) -> None:
        self.election_deadline = time.monotonic() + random.uniform(*self.election_timeout_bounds)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.reset_election_timer()
        self.last_heartbeat_sent = 0.0
        self._thread = threading.Thread(target=self._loop, name=f"raft-{self.node.peer_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False

    def is_leader(self) -> bool:
        with self.lock:
            return self.node.role == "leader"

    def note_leader(self, leader_id: int) -> None:
        self.known_leader_id = leader_id

    def trading_address(self, peer_id: int) -> str | None:
        return self.peers.trading_addresses.get(peer_id)

    def not_leader_detail(self) -> str:
        with self.lock:
            if self.node.role == "leader":
                addr = self.trading_address(self.node.peer_id)
                return f"NOT_LEADER;trading={addr or 'unknown'}"
            leader_id = self.known_leader_id
        if leader_id is not None:
            addr = self.trading_address(leader_id)
            if addr:
                return f"NOT_LEADER;trading={addr}"
        return "NOT_LEADER;trading=unknown"

    def _follower_ids(self) -> list[int]:
        return [pid for pid in self.peers.peer_ids() if pid != self.node.peer_id]

    def _init_leader_tracking(self) -> None:
        self.next_index, self.match_index = init_leader_tracking(self.node, self._follower_ids())

    def _send_append_local(
        self, pid: int, term: int, prev_index: int, prev_term: int, commit: int, entries: list[LogEntry]
    ) -> dict[str, int | bool]:
        reply = self._rpc_append_entries(
            pid,
            term=term,
            prev_index=prev_index,
            prev_term=prev_term,
            leader_commit=commit,
            entries=entries,
        )
        if reply is None:
            return {"entry_appended": False, "match_index": 0, "term": term}
        return {
            "entry_appended": reply.entry_appended,
            "match_index": int(reply.match_index),
            "term": int(reply.term),
        }

    def replicate_command(self, command: Command) -> bool:
        with self.lock:
            if self.node.role != "leader":
                return False
            entry = LogEntry(self.node.current_term, encode_command(command))
            followers = self._follower_ids()

            def send(pid, term, prev_index, prev_term, commit, entries):
                return self._send_append_local(pid, term, prev_index, prev_term, commit, entries)

            ok = replicate_entry(self.node, entry, followers, send, self.next_index, self.match_index)
            if ok:
                push_commit_to_followers(self.node, followers, send, self.next_index, self.match_index)
            return ok

    def replicate_admin_reset(self, seed_path: str) -> bool:
        with self.lock:
            if self.node.role != "leader":
                return False
            entry = LogEntry(self.node.current_term, encode_admin_reset(seed_path))
            followers = self._follower_ids()

            def send(pid, term, prev_index, prev_term, commit, entries):
                return self._send_append_local(pid, term, prev_index, prev_term, commit, entries)

            ok = replicate_entry(self.node, entry, followers, send, self.next_index, self.match_index)
            if ok:
                push_commit_to_followers(self.node, followers, send, self.next_index, self.match_index)
            return ok

    def _loop(self) -> None:
        while self.running:
            time.sleep(0.05)
            with self.lock:
                now = time.monotonic()
                if self.node.role == "leader":
                    if now >= self.last_heartbeat_sent + self.heartbeat_interval:
                        self._send_heartbeats()
                        self.last_heartbeat_sent = now
                elif now >= self.election_deadline:
                    self._run_election()

    def _run_election(self) -> None:
        term = self.node.begin_election()
        votes = 1
        for pid in self.peers.peer_ids():
            if pid == self.node.peer_id:
                continue
            reply = self._rpc_request_vote(pid, term)
            if reply is None:
                continue
            if reply.term > term:
                self.node.current_term = reply.term
                self.node.role = "follower"
                self.node.voted_for = None
                self.reset_election_timer()
                return
            if reply.vote_granted:
                votes += 1

        if votes > len(self.peers.peer_ids()) // 2:
            self.node.become_leader()
            self._init_leader_tracking()
            self.last_heartbeat_sent = 0.0
            self._send_heartbeats()
        else:
            self.reset_election_timer()

    def _send_heartbeats(self) -> None:
        followers = self._follower_ids()
        if not followers:
            return

        def send(pid, term, prev_index, prev_term, commit, entries):
            return self._send_append_local(pid, term, prev_index, prev_term, commit, entries)

        push_commit_to_followers(self.node, followers, send, self.next_index, self.match_index)

    def _rpc_request_vote(self, to_peer: int, term: int) -> raft_pb2.RequestVoteReply | None:
        try:
            return self.peers.stub(to_peer).RequestVote(
                raft_pb2.RequestVoteRequest(
                    **{
                        "from": self.node.peer_id,
                        "to": to_peer,
                        "term": term,
                        "last_log_index": self.node.last_log_index(),
                        "last_log_term": self.node.last_log_term(),
                    }
                ),
                timeout=0.5,
            )
        except grpc.RpcError:
            return None

    def _rpc_append_entries(
        self,
        to_peer: int,
        *,
        term: int,
        prev_index: int,
        prev_term: int,
        leader_commit: int,
        entries: list[LogEntry],
    ) -> raft_pb2.AppendEntriesReply | None:
        try:
            return self.peers.stub(to_peer).AppendEntries(
                raft_pb2.AppendEntriesRequest(
                    **{
                        "from": self.node.peer_id,
                        "to": to_peer,
                        "term": term,
                        "prev_index": prev_index,
                        "prev_term": prev_term,
                        "commit_index": leader_commit,
                        "entries": [
                            raft_pb2.LogEntry(term=e.term, command=e.command) for e in entries
                        ],
                    }
                ),
                timeout=0.5,
            )
        except grpc.RpcError:
            return None
