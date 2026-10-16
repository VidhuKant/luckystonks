from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class PeerEndpoint:
    peer_id: int
    raft_addr: str
    trading_addr: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> PeerEndpoint:
        return cls(
            peer_id=int(row["peer_id"]),
            raft_addr=str(row["raft_addr"]),
            trading_addr=str(row["trading_addr"]),
        )


def endpoints_from_maps(raft: dict[int, str], trading: dict[int, str]) -> list[PeerEndpoint]:
    peers = sorted(set(raft.keys()) | set(trading.keys()))
    return [
        PeerEndpoint(pid, raft[pid], trading.get(pid, ""))
        for pid in peers
        if pid in raft
    ]


def maps_from_endpoints(endpoints: list[PeerEndpoint]) -> tuple[dict[int, str], dict[int, str]]:
    raft: dict[int, str] = {}
    trading: dict[int, str] = {}
    for ep in endpoints:
        raft[ep.peer_id] = ep.raft_addr
        if ep.trading_addr:
            trading[ep.peer_id] = ep.trading_addr
    return raft, trading
