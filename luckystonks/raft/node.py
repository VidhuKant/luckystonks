from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command

from .codec import apply_log_entry, encode_command
from .log_entry import LogEntry

Role = Literal["follower", "candidate", "leader"]


class RaftNode:
    def __init__(self, peer_id: int, engine: Engine) -> None:
        self.peer_id = peer_id
        self.engine = engine
        self.current_term: int = 0
        self.voted_for: int | None = None
        self.role: Role = "follower"
        self.log: list[LogEntry] = []
        self.commit_index: int = 0
        self.last_applied: int = 0
        self.raft_state_path: Path | None = None
        self.admin_reset_hooks: list[Callable[[], None]] = []

    def last_log_index(self) -> int:
        return len(self.log)

    def last_log_term(self) -> int:
        if not self.log:
            return 0
        return self.log[-1].term

    def handle_append_entries(
        self,
        *,
        from_peer: int,
        to_peer: int,
        term: int,
        prev_index: int,
        prev_term: int,
        leader_commit: int,
        entries: list[LogEntry],
    ) -> dict[str, int | bool]:
        if term < self.current_term:
            return self._append_reply(from_peer, False, self.last_log_index())

        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.role = "follower"

        if prev_index > 0:
            if prev_index > len(self.log) or self.log[prev_index - 1].term != prev_term:
                return self._append_reply(from_peer, False, self.last_log_index())

        if entries:
            self.log = self.log[:prev_index]
            self.log.extend(entries)

        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, self.last_log_index())

        self._apply_committed()
        self._maybe_persist()
        return self._append_reply(from_peer, True, self.last_log_index())

    def leader_propose(self, command: Command, term: int | None = None) -> dict[str, int | bool]:
        use_term = term if term is not None else max(self.current_term, 1)
        self.current_term = use_term
        self.role = "leader"
        prev_index = self.last_log_index()
        prev_term = self.last_log_term()
        new_entry = LogEntry(use_term, encode_command(command))
        new_index = prev_index + 1
        return self.handle_append_entries(
            from_peer=self.peer_id,
            to_peer=self.peer_id,
            term=use_term,
            prev_index=prev_index,
            prev_term=prev_term,
            leader_commit=new_index,
            entries=[new_entry],
        )

    def _apply_committed(self) -> None:
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied - 1]
            if not entry.command:
                continue
            apply_log_entry(self.engine, entry.command, self.admin_reset_hooks)
        self._maybe_persist()

    def _maybe_persist(self) -> None:
        if self.raft_state_path is not None:
            from .persist import save_raft_state

            save_raft_state(self.raft_state_path, self)

    def _append_reply(self, to_peer: int, success: bool, match_index: int) -> dict[str, int | bool]:
        return {
            "from": self.peer_id,
            "to": to_peer,
            "term": self.current_term,
            "entry_appended": success,
            "match_index": match_index,
        }

    def start(self) -> None:
        raise NotImplementedError

    def request_vote(self, **kwargs: object) -> dict:
        return self.handle_request_vote(
            from_peer=int(kwargs["from_peer"]),
            to_peer=int(kwargs["to_peer"]),
            term=int(kwargs["term"]),
            last_log_index=int(kwargs["last_log_index"]),
            last_log_term=int(kwargs["last_log_term"]),
        )

    def append_entries(self, **kwargs: object) -> dict:
        raise NotImplementedError

    def submit_client_post(self, **kwargs: object) -> object:
        raise NotImplementedError

    def _candidate_log_up_to_date(self, last_log_index: int, last_log_term: int) -> bool:
        if last_log_term != self.last_log_term():
            return last_log_term > self.last_log_term()
        return last_log_index >= self.last_log_index()

    def begin_election(self) -> int:
        self.current_term += 1
        self.role = "candidate"
        self.voted_for = self.peer_id
        self._maybe_persist()
        return self.current_term

    def handle_request_vote(
        self,
        *,
        from_peer: int,
        to_peer: int,
        term: int,
        last_log_index: int,
        last_log_term: int,
    ) -> dict[str, int | bool]:
        if term < self.current_term:
            return self._vote_reply(from_peer, False)

        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.role = "follower"

        grant = False
        if (self.voted_for is None or self.voted_for == from_peer) and self._candidate_log_up_to_date(
            last_log_index, last_log_term
        ):
            self.voted_for = from_peer
            grant = True
            self._maybe_persist()

        return self._vote_reply(from_peer, grant)

    def become_leader(self) -> None:
        self.role = "leader"

    def _vote_reply(self, to_peer: int, vote_granted: bool) -> dict[str, int | bool]:
        return {
            "from": self.peer_id,
            "to": to_peer,
            "term": self.current_term,
            "vote_granted": vote_granted,
        }