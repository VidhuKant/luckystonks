"""Raft node stub — leader election and log replication in phase 2."""

from __future__ import annotations

from luckystonks.matching.engine import Engine


class RaftNode:
    """One peer in the trading cluster; wraps Engine apply after commit."""

    def __init__(self, peer_id: int, engine: Engine) -> None:
        self.peer_id = peer_id
        self.engine = engine

    def start(self) -> None:
        """Begin follower/candidate/leader loop and gRPC peer server."""
        raise NotImplementedError

    def request_vote(self, **kwargs: object) -> dict:
        """Handle incoming RequestVote RPC."""
        raise NotImplementedError

    def append_entries(self, **kwargs: object) -> dict:
        """Handle incoming AppendEntries RPC."""
        raise NotImplementedError

    def submit_client_post(self, **kwargs: object) -> object:
        """Leader path: append log entry, replicate, then engine.apply."""
        raise NotImplementedError
