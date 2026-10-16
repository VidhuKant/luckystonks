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


def load_trading_peers_from_env(raft_peers: dict[int, str] | None = None) -> dict[int, str]:
    spec = os.getenv("TRADING_PEERS", "")
    host = os.getenv("TRADING_HOST", os.getenv("RAFT_HOST", "127.0.0.1"))
    if spec:
        return parse_raft_peers(spec, default_host=host)
    raft_peers = raft_peers or load_raft_peers_from_env()
    trading: dict[int, str] = {}
    for pid in raft_peers:
        trading[pid] = f"{host}:{50051 + pid}"
    return trading


class PeerRegistry:
    def __init__(
        self,
        peer_id: int,
        addresses: dict[int, str],
        trading_addresses: dict[int, str] | None = None,
    ) -> None:
        self.peer_id = peer_id
        self.addresses = dict(addresses)
        self.trading_addresses = dict(trading_addresses or {})
        self._stubs: dict[int, raft_pb2_grpc.RaftStub] = {}

    def peer_ids(self) -> list[int]:
        return sorted(self.addresses.keys())

    def quorum_size(self) -> int:
        return len(self.peer_ids()) // 2 + 1

    def stub(self, peer_id: int) -> raft_pb2_grpc.RaftStub:
        if peer_id not in self.addresses:
            raise KeyError(f"unknown peer id {peer_id}")
        if peer_id not in self._stubs:
            channel = grpc.insecure_channel(self.addresses[peer_id])
            self._stubs[peer_id] = raft_pb2_grpc.RaftStub(channel)
        return self._stubs[peer_id]

    def drop_stub(self, peer_id: int) -> None:
        self._stubs.pop(peer_id, None)

    def apply_config_change(self, payload: dict[str, str | int]) -> None:
        action = str(payload["action"])
        peer_id = int(payload["peer_id"])
        raft_addr = str(payload["raft_addr"])
        trading_addr = str(payload.get("trading_addr") or "")
        if action == "add":
            self.addresses[peer_id] = raft_addr
            if trading_addr:
                self.trading_addresses[peer_id] = trading_addr
            self.drop_stub(peer_id)
            return
        if action == "remove":
            if peer_id == self.peer_id:
                raise ValueError("cannot remove self from cluster via config entry")
            self.addresses.pop(peer_id, None)
            self.trading_addresses.pop(peer_id, None)
            self.drop_stub(peer_id)
            return
        raise ValueError(f"unknown config action: {action}")

    def sync_from_endpoints(self, endpoints: list) -> None:
        from .cluster_config import maps_from_endpoints

        raft, trading = maps_from_endpoints(endpoints)
        self.addresses = raft
        self.trading_addresses = trading
        self._stubs.clear()
