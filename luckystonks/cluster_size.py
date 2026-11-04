"""Configurable Raft/trading cluster size (demo default: 5; switchable to 3)."""

from __future__ import annotations

import os

ALLOWED_SIZES = frozenset({3, 5})
DEFAULT_CLUSTER_SIZE = 5
BASE_TRADING_PORT = 50051
BASE_RAFT_PORT = 60051


def cluster_size() -> int:
    raw = os.getenv("CLUSTER_SIZE", str(DEFAULT_CLUSTER_SIZE)).strip()
    try:
        size = int(raw)
    except ValueError as err:
        raise ValueError(f"CLUSTER_SIZE must be an integer, got {raw!r}") from err
    if size not in ALLOWED_SIZES:
        raise ValueError(f"CLUSTER_SIZE must be one of {sorted(ALLOWED_SIZES)}, got {size}")
    return size


def peer_ids(size: int | None = None) -> list[int]:
    n = cluster_size() if size is None else size
    if n not in ALLOWED_SIZES:
        raise ValueError(f"cluster size must be one of {sorted(ALLOWED_SIZES)}, got {n}")
    return list(range(n))


def trading_port(peer_id: int) -> int:
    return BASE_TRADING_PORT + peer_id


def raft_port(peer_id: int) -> int:
    return BASE_RAFT_PORT + peer_id


def raft_peers_env(host: str = "127.0.0.1", size: int | None = None) -> str:
    return ",".join(f"{i}={host}:{raft_port(i)}" for i in peer_ids(size))


def trading_peers_env(host: str = "127.0.0.1", size: int | None = None) -> str:
    return ",".join(f"{i}={host}:{trading_port(i)}" for i in peer_ids(size))


def quorum(size: int | None = None) -> int:
    n = cluster_size() if size is None else size
    return n // 2 + 1
