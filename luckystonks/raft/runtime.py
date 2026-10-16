from __future__ import annotations

import random
import threading
import time
from typing import TYPE_CHECKING

import grpc

from luckystonks.matching.models import Command
from luckystonks.pb import raft_pb2

from .codec import encode_admin_reset, encode_command
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

    def replicate_command(self, command: Command) -> bool:
        with self.lock:
            if self.node.role != "leader":
                return False
            term = self.node.current_term
            prev_index = self.node.last_log_index()
            prev_term = self.node.last_log_term()
            entry = LogEntry(term, encode_command(command))
            new_index = prev_index + 1
            self.node.log.append(entry)

            successes = 1
            for pid in self.peers.peer_ids():
                if pid == self.node.peer_id:
                    continue
                reply = self._rpc_append_entries(
                    pid,
                    term=term,
                    prev_index=prev_index,
                    prev_term=prev_term,
                    leader_commit=0,
                    entries=[entry],
                )
                if reply is not None and reply.entry_appended:
                    successes += 1

            if successes <= len(self.peers.peer_ids()) // 2:
                self.node.log.pop()
                return False

            for pid in self.peers.peer_ids():
                self._rpc_append_entries(
                    pid,
                    term=term,
                    prev_index=new_index,
                    prev_term=term,
                    leader_commit=new_index,
                    entries=[],
                )
            self.node.commit_index = new_index
            self.node._apply_committed()
            return True

    def replicate_admin_reset(self, seed_path: str) -> bool:
        with self.lock:
            if self.node.role != "leader":
                return False
            term = self.node.current_term
            prev_index = self.node.last_log_index()
            prev_term = self.node.last_log_term()
            entry = LogEntry(term, encode_admin_reset(seed_path))
            new_index = prev_index + 1
            self.node.log.append(entry)

            successes = 1
            for pid in self.peers.peer_ids():
                if pid == self.node.peer_id:
                    continue
                reply = self._rpc_append_entries(
                    pid,
                    term=term,
                    prev_index=prev_index,
                    prev_term=prev_term,
                    leader_commit=0,
                    entries=[entry],
                )
                if reply is not None and reply.entry_appended:
                    successes += 1

            if successes <= len(self.peers.peer_ids()) // 2:
                self.node.log.pop()
                return False

            for pid in self.peers.peer_ids():
                self._rpc_append_entries(
                    pid,
                    term=term,
                    prev_index=new_index,
                    prev_term=term,
                    leader_commit=new_index,
                    entries=[],
                )
            self.node.commit_index = new_index
            self.node._apply_committed()
            return True

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
            self.last_heartbeat_sent = 0.0
            self._send_heartbeats()
        else:
            self.reset_election_timer()

    def _send_heartbeats(self) -> None:
        term = self.node.current_term
        prev_index = self.node.last_log_index()
        prev_term = self.node.last_log_term()
        commit = self.node.commit_index
        for pid in self.peers.peer_ids():
            if pid == self.node.peer_id:
                continue
            self._rpc_append_entries(
                pid,
                term=term,
                prev_index=prev_index,
                prev_term=prev_term,
                leader_commit=commit,
                entries=[],
            )

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
