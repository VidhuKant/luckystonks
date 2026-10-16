from __future__ import annotations

import os

import grpc

from luckystonks.pb import raft_pb2_grpc


def parse_raft_peers(spec: str, default_host: str = "127.0.0.1") -> dict[int, str]:
    peers: dict[int, str] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            pid_s, addr = part.split("=", 1)
            peers[int(pid_s.strip())] = addr.strip()
            continue
        if ":" not in part:
            raise ValueError(f"invalid raft peer spec fragment: {part}")
        pid_s, port_s = part.split(":", 1)
        peers[int(pid_s.strip())] = f"{default_host}:{port_s.strip()}"
    if not peers:
        raise ValueError("RAFT_PEERS must list at least one peer")
    return peers


def load_raft_peers_from_env() -> dict[int, str]:
    spec = os.getenv("RAFT_PEERS", "")
    if not spec:
        raise ValueError("RAFT_PEERS is required when RAFT_ENABLED=1")
    host = os.getenv("RAFT_HOST", "127.0.0.1")
    return parse_raft_peers(spec, default_host=host)


class PeerRegistry:
    def __init__(self, peer_id: int, addresses: dict[int, str]) -> None:
        self.peer_id = peer_id
        self.addresses = addresses
        self._stubs: dict[int, raft_pb2_grpc.RaftStub] = {}

    def peer_ids(self) -> list[int]:
        return sorted(self.addresses.keys())

    def stub(self, peer_id: int) -> raft_pb2_grpc.RaftStub:
        if peer_id not in self.addresses:
            raise KeyError(f"unknown peer id {peer_id}")
        if peer_id not in self._stubs:
            channel = grpc.insecure_channel(self.addresses[peer_id])
            self._stubs[peer_id] = raft_pb2_grpc.RaftStub(channel)
        return self._stubs[peer_id]
