from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import grpc

from luckystonks.matching.models import Command
from luckystonks.pb import raft_pb2

from .cluster_config import PeerEndpoint
from .codec import encode_admin_reset, encode_command, encode_config_change
from .snapshot import DEFAULT_COMPACT_THRESHOLD
from .leader_replicate import (
    init_leader_tracking,
    push_commit_to_followers,
    replicate_entry,
)
from .log_entry import LogEntry
from .log_util import raft_logger
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
        self.last_status_export = 0.0
        self.status_export_interval = 0.2
        # Paper: heartbeat ≪ election timeout; randomized election timeouts avoid split votes.
        self.heartbeat_interval = float(os.getenv("RAFT_HEARTBEAT_INTERVAL", "0.5"))
        self.election_timeout_bounds = (
            float(os.getenv("RAFT_ELECTION_TIMEOUT_MIN", "3.0")),
            float(os.getenv("RAFT_ELECTION_TIMEOUT_MAX", "5.0")),
        )
        self.election_timeout_drawn = 0.0
        self.known_leader_id: int | None = None
        self.next_index: dict[int, int] = {}
        self.match_index: dict[int, int] = {}
        self.log = raft_logger(node.peer_id)
        self.node.compact_threshold = int(
            os.getenv("RAFT_LOG_COMPACT_THRESHOLD", str(DEFAULT_COMPACT_THRESHOLD))
        )

    def reset_election_timer(self) -> None:
        drawn = random.uniform(*self.election_timeout_bounds)
        self.election_timeout_drawn = drawn
        self.election_deadline = time.monotonic() + drawn
        # Heartbeats reset this often; rely on the status loop (~0.2s) for UI countdown.

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.reset_election_timer()
        self.last_heartbeat_sent = 0.0
        self._thread = threading.Thread(target=self._loop, name=f"raft-{self.node.peer_id}", daemon=True)
        self._thread.start()
        self._export_status_unlocked()
        self.log.info(
            "raft runtime started role=%s term=%s commit=%s log_len=%s",
            self.node.role,
            self.node.current_term,
            self.node.commit_index,
            self.node.last_log_index(),
        )

    def stop(self) -> None:
        self.running = False
        with self.lock:
            self._export_status_unlocked()

    def status_snapshot(self) -> dict[str, Any]:
        with self.lock:
            return self._status_dict_unlocked()

    def _status_path(self) -> Path | None:
        path = self.node.raft_state_path
        if path is None:
            return None
        return Path(path).parent / f"raft-status-peer{self.node.peer_id}.json"

    def _status_dict_unlocked(self) -> dict[str, Any]:
        role = self.node.role
        now_mono = time.monotonic()
        now_wall = time.time()
        election_remaining = max(0.0, self.election_deadline - now_mono)
        lo, hi = self.election_timeout_bounds
        payload: dict[str, Any] = {
            "peer_id": self.node.peer_id,
            "role": role,
            "currentTerm": self.node.current_term,
            "votedFor": self.node.voted_for,
            "commitIndex": self.node.commit_index,
            "lastApplied": self.node.last_applied,
            "lastLogIndex": self.node.last_log_index(),
            "lastLogTerm": self.node.last_log_term(),
            "logLen": len(self.node.log),
            "snapshotLastIncludedIndex": self.node.snapshot_last_included_index,
            "snapshotLastIncludedTerm": self.node.snapshot_last_included_term,
            "knownLeaderId": self.known_leader_id,
            "clusterSize": self._cluster_size(),
            "nextIndex": None,
            "matchIndex": None,
            "electionTimeoutMin": lo,
            "electionTimeoutMax": hi,
            "electionTimeoutSec": round(self.election_timeout_drawn, 3),
            "electionRemainingSec": round(election_remaining, 3),
            "electionDeadlineAt": now_wall + election_remaining,
            "heartbeatIntervalSec": self.heartbeat_interval,
            "heartbeatRemainingSec": None,
            "heartbeatDeadlineAt": None,
            "ts": now_wall,
        }
        if role == "leader":
            payload["nextIndex"] = {str(k): int(v) for k, v in sorted(self.next_index.items())}
            payload["matchIndex"] = {str(k): int(v) for k, v in sorted(self.match_index.items())}
            hb_remaining = max(
                0.0,
                self.last_heartbeat_sent + self.heartbeat_interval - now_mono,
            )
            payload["heartbeatRemainingSec"] = round(hb_remaining, 3)
            payload["heartbeatDeadlineAt"] = now_wall + hb_remaining
            # Leaders do not run the election countdown; clear for UI clarity.
            payload["electionRemainingSec"] = None
            payload["electionDeadlineAt"] = None
        return payload

    def _export_status_unlocked(self) -> None:
        status_path = self._status_path()
        if status_path is None:
            return
        try:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                json.dumps(self._status_dict_unlocked(), indent=2),
                encoding="utf-8",
            )
            self.last_status_export = time.monotonic()
        except OSError:
            pass

    def is_leader(self) -> bool:
        with self.lock:
            return self.node.role == "leader"

    def note_leader(self, leader_id: int) -> None:
        if leader_id == self.node.peer_id and self.node.role != "leader":
            return
        if self.known_leader_id != leader_id:
            self.log.debug("known leader updated peer=%s", leader_id)
        self.known_leader_id = leader_id
        if self.node.role != "leader":
            self.reset_election_timer()

    def _step_down(self, new_term: int) -> None:
        if new_term > self.node.current_term:
            self.log.info("stepping down: adopting term=%s (was leader=%s)", new_term, self.node.role)
            self.node.current_term = new_term
        self.node.role = "follower"
        self.node.voted_for = None
        self.known_leader_id = None
        self.reset_election_timer()
        self._export_status_unlocked()

    def trading_address(self, peer_id: int) -> str | None:
        return self.peers.trading_addresses.get(peer_id)

    def not_leader_detail(self) -> str:
        with self.lock:
            leader_id = self.known_leader_id
            if leader_id is not None and leader_id == self.node.peer_id:
                leader_id = None
            if leader_id is not None:
                addr = self.trading_address(leader_id)
                if addr:
                    return f"NOT_LEADER;trading={addr}"
        for pid in sorted(self.peers.peer_ids()):
            if pid == self.node.peer_id:
                continue
            addr = self.trading_address(pid)
            if addr:
                return f"NOT_LEADER;trading={addr}"
        return "NOT_LEADER;trading=unknown"

    def _follower_ids(self) -> list[int]:
        return [pid for pid in self.peers.peer_ids() if pid != self.node.peer_id]

    def _init_leader_tracking(self) -> None:
        self.next_index, self.match_index = init_leader_tracking(self.node, self._follower_ids())

    def _on_config_change(self, payload: dict[str, str | int]) -> None:
        self.peers.apply_config_change(payload)
        ep = PeerEndpoint(
            int(payload["peer_id"]),
            str(payload["raft_addr"]),
            str(payload.get("trading_addr") or ""),
        )
        action = str(payload["action"])
        existing = {e.peer_id: e for e in self.node.cluster_endpoints}
        if action == "add":
            existing[ep.peer_id] = ep
        elif action == "remove":
            existing.pop(ep.peer_id, None)
        self.node.cluster_endpoints = [existing[i] for i in sorted(existing)]
        if self.node.role == "leader":
            self._init_leader_tracking()

    def _cluster_size(self) -> int:
        return len(self.peers.peer_ids())

    def _rpc_call_without_lock(self, fn):
        """Run an RPC while releasing self.lock so inbound Raft RPCs can proceed.

        Caller must hold self.lock. Re-acquires before returning.
        """
        self.lock.release()
        try:
            return fn()
        finally:
            self.lock.acquire()

    def _send_snapshot_local(
        self,
        pid: int,
        term: int,
        last_included_index: int,
        last_included_term: int,
        data: bytes,
    ) -> dict[str, int | bool] | None:
        reply = self._rpc_call_without_lock(
            lambda: self._rpc_install_snapshot(
                pid,
                term=term,
                last_included_index=last_included_index,
                last_included_term=last_included_term,
                data=data,
            )
        )
        if reply is None:
            return None
        reply_term = int(reply.term)
        if reply_term > self.node.current_term:
            self._step_down(reply_term)
        return {"entry_appended": True, "match_index": last_included_index, "term": reply_term}

    def _send_append_local(
        self, pid: int, term: int, prev_index: int, prev_term: int, commit: int, entries: list[LogEntry]
    ) -> dict[str, int | bool] | None:
        is_heartbeat = len(entries) == 0
        reply = self._rpc_call_without_lock(
            lambda: self._rpc_append_entries(
                pid,
                term=term,
                prev_index=prev_index,
                prev_term=prev_term,
                leader_commit=commit,
                entries=entries,
                heartbeat=is_heartbeat,
            )
        )
        if reply is None:
            return None
        reply_term = int(reply.term)
        if reply_term > self.node.current_term:
            self._step_down(reply_term)
        return {
            "entry_appended": reply.entry_appended,
            "match_index": int(reply.match_index),
            "term": reply_term,
        }

    def replicate_command(self, command: Command) -> bool:
        with self.lock:
            if self.node.role != "leader":
                self.log.info("replicate command rejected: not leader (role=%s)", self.node.role)
                return False
            self.log.info(
                "replicate command start client_request_id=%s user=%s",
                command.client_request_id,
                command.user_id,
            )
            entry = LogEntry(self.node.current_term, encode_command(command))
            followers = self._follower_ids()

            def send(pid, term, prev_index, prev_term, commit, entries):
                return self._send_append_local(pid, term, prev_index, prev_term, commit, entries)

            ok = replicate_entry(
                self.node,
                entry,
                followers,
                send,
                self.next_index,
                self.match_index,
                self._cluster_size(),
                self._send_snapshot_local,
                self.log,
            )
            if self.node.role != "leader":
                self.log.info("replicate command aborted: stepped down")
                return False
            if ok:
                push_commit_to_followers(
                    self.node,
                    followers,
                    send,
                    self.next_index,
                    self.match_index,
                    self._send_snapshot_local,
                    self.log,
                )
                self.log.info(
                    "replicate command ok commit=%s log_len=%s",
                    self.node.commit_index,
                    self.node.last_log_index(),
                )
            else:
                self.log.info("replicate command failed")
            return ok

    def replicate_admin_reset(self, seed_path: str) -> bool:
        with self.lock:
            if self.node.role != "leader":
                self.log.info("replicate admin reset rejected: not leader (role=%s)", self.node.role)
                return False
            self.log.info("replicate admin reset start seed=%s", seed_path)
            entry = LogEntry(self.node.current_term, encode_admin_reset(seed_path))
            followers = self._follower_ids()

            def send(pid, term, prev_index, prev_term, commit, entries):
                return self._send_append_local(pid, term, prev_index, prev_term, commit, entries)

            ok = replicate_entry(
                self.node,
                entry,
                followers,
                send,
                self.next_index,
                self.match_index,
                self._cluster_size(),
                self._send_snapshot_local,
                self.log,
            )
            if self.node.role != "leader":
                self.log.info("replicate admin reset aborted: stepped down")
                return False
            if ok:
                push_commit_to_followers(
                    self.node,
                    followers,
                    send,
                    self.next_index,
                    self.match_index,
                    self._send_snapshot_local,
                    self.log,
                )
                self.log.info(
                    "replicate admin reset ok commit=%s",
                    self.node.commit_index,
                )
            else:
                self.log.info("replicate admin reset failed")
            return ok

    def replicate_config_change(
        self, action: str, peer_id: int, raft_addr: str, trading_addr: str
    ) -> bool:
        with self.lock:
            if self.node.role != "leader":
                self.log.info("replicate config rejected: not leader (role=%s)", self.node.role)
                return False
            if action == "remove" and peer_id == self.node.peer_id:
                return False
            if action == "add" and peer_id in self.peers.peer_ids():
                return False
            if action == "remove" and peer_id not in self.peers.peer_ids():
                return False
            self.log.info(
                "replicate config change action=%s peer_id=%s",
                action,
                peer_id,
            )
            entry = LogEntry(
                self.node.current_term,
                encode_config_change(action, peer_id, raft_addr, trading_addr),
            )
            followers = self._follower_ids()

            def send(pid, term, prev_index, prev_term, commit, entries):
                return self._send_append_local(pid, term, prev_index, prev_term, commit, entries)

            ok = replicate_entry(
                self.node,
                entry,
                followers,
                send,
                self.next_index,
                self.match_index,
                self._cluster_size(),
                self._send_snapshot_local,
                self.log,
            )
            if self.node.role != "leader":
                return False
            if ok:
                push_commit_to_followers(
                    self.node,
                    followers,
                    send,
                    self.next_index,
                    self.match_index,
                    self._send_snapshot_local,
                    self.log,
                )
            return ok

    def _loop(self) -> None:
        while self.running:
            time.sleep(0.05)
            do_heartbeat = False
            do_election = False
            with self.lock:
                now = time.monotonic()
                if self.node.role == "leader":
                    if now >= self.last_heartbeat_sent + self.heartbeat_interval:
                        do_heartbeat = True
                elif now >= self.election_deadline:
                    do_election = True
                if now >= self.last_status_export + self.status_export_interval:
                    self._export_status_unlocked()
            # Never hold the Raft lock across network I/O (avoids deadlock with inbound RPCs).
            if do_election:
                self._run_election()
            elif do_heartbeat:
                self._send_heartbeats()

    def _run_election(self) -> None:
        with self.lock:
            term = self.node.begin_election()
            cluster_size = self._cluster_size()
            quorum = cluster_size // 2 + 1
            peer_ids = [pid for pid in self.peers.peer_ids() if pid != self.node.peer_id]
            self.log.info("election started term=%s need_votes=%s", term, quorum)
            votes = 1

        for pid in peer_ids:
            reply = self._rpc_request_vote(pid, term)
            with self.lock:
                if self.node.role != "candidate" or self.node.current_term != term:
                    return
                if reply is None:
                    self.log.info("vote rpc to peer=%s term=%s result=timeout", pid, term)
                    continue
                if reply.term > term:
                    self.log.info(
                        "election aborted: peer=%s sent higher term=%s (was %s)",
                        pid,
                        reply.term,
                        term,
                    )
                    self.node.current_term = reply.term
                    self.node.role = "follower"
                    self.node.voted_for = None
                    self.reset_election_timer()
                    self._export_status_unlocked()
                    return
                if reply.vote_granted:
                    votes += 1
                    self.log.info("vote rpc to peer=%s term=%s result=granted", pid, term)
                else:
                    self.log.info("vote rpc to peer=%s term=%s result=denied", pid, term)

        became_leader = False
        with self.lock:
            if self.node.role != "candidate" or self.node.current_term != term:
                return
            if votes > cluster_size // 2:
                self.node.become_leader()
                self._init_leader_tracking()
                self.last_heartbeat_sent = 0.0
                self.log.info(
                    "became leader term=%s commit=%s log_len=%s",
                    self.node.current_term,
                    self.node.commit_index,
                    self.node.last_log_index(),
                )
                self._export_status_unlocked()
                became_leader = True
            else:
                self.log.info(
                    "election failed term=%s votes=%s need=%s",
                    term,
                    votes,
                    cluster_size // 2 + 1,
                )
                self.reset_election_timer()
                self._export_status_unlocked()

        if became_leader:
            self._send_heartbeats()

    def _send_heartbeats(self) -> None:
        with self.lock:
            if self.node.role != "leader":
                return
            followers = self._follower_ids()
            # Stamp at START so Ops remaining counts down during slow RPCs to DOWN
            # peers instead of sitting at 0 for the whole sequential round.
            self.last_heartbeat_sent = time.monotonic()
            self._export_status_unlocked()
            if not followers:
                return
            term = self.node.current_term
            commit = self.node.commit_index
            log_len = self.node.last_log_index()
            self.log.info(
                "heartbeat term=%s commit=%s log_len=%s followers=%s",
                term,
                commit,
                log_len,
                followers,
            )

            def send(pid, t, prev_index, prev_term, cmt, entries):
                return self._send_append_local(pid, t, prev_index, prev_term, cmt, entries)

            push_commit_to_followers(
                self.node,
                followers,
                send,
                self.next_index,
                self.match_index,
                self._send_snapshot_local,
                self.log,
            )
            self._export_status_unlocked()

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
                timeout=0.25,
            )
        except grpc.RpcError as err:
            self.log.info("request vote to peer=%s failed: %s", to_peer, err.code())
            self.peers.drop_stub(to_peer)
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
        heartbeat: bool = False,
    ) -> raft_pb2.AppendEntriesReply | None:
        # Heartbeats to a stopped peer must fail fast so other followers stay fed.
        rpc_timeout = 0.2 if heartbeat else 0.5
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
                timeout=rpc_timeout,
            )
        except grpc.RpcError as err:
            self.peers.drop_stub(to_peer)
            if heartbeat:
                self.log.info(
                    "heartbeat to peer=%s failed: %s",
                    to_peer,
                    err.code(),
                )
            else:
                self.log.info(
                    "append entries to peer=%s failed: %s (entries=%s)",
                    to_peer,
                    err.code(),
                    len(entries),
                )
            return None

    def _rpc_install_snapshot(
        self,
        to_peer: int,
        *,
        term: int,
        last_included_index: int,
        last_included_term: int,
        data: bytes,
    ) -> raft_pb2.InstallSnapshotReply | None:
        try:
            return self.peers.stub(to_peer).InstallSnapshot(
                raft_pb2.InstallSnapshotRequest(
                    **{
                        "from": self.node.peer_id,
                        "to": to_peer,
                        "term": term,
                        "last_included_index": last_included_index,
                        "last_included_term": last_included_term,
                        "data": data,
                        "done": True,
                    }
                ),
                timeout=2.0,
            )
        except grpc.RpcError as err:
            self.log.info(
                "install snapshot to peer=%s failed: %s",
                to_peer,
                err.code(),
            )
            return None
