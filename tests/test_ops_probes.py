"""Ops cluster probes must stay fast when peers are down."""

from __future__ import annotations

import time
from pathlib import Path

from web.grpc_client import probe_port_listening
from web.ops_state import build_cluster_status


def test_probe_port_listening_closed_is_fast():
    t0 = time.perf_counter()
    ok = probe_port_listening("127.0.0.1", 1, timeout=0.15)
    elapsed = time.perf_counter() - t0
    assert ok is False
    assert elapsed < 0.5


def test_build_cluster_status_parallel_probes_with_down_peers(tmp_path: Path):
    calls: list[tuple[str, int]] = []

    def slow_down_probe(host: str, port: int) -> bool:
        calls.append((host, port))
        # Simulate a dead port without actually blocking 0.8s.
        time.sleep(0.12)
        return False

    t0 = time.perf_counter()
    status = build_cluster_status(
        root=tmp_path,
        log_dir=tmp_path / "logs",
        pid_file=tmp_path / "pids.json",
        host="127.0.0.1",
        probe_trading=slow_down_probe,
        probe_raft=slow_down_probe,
    )
    elapsed = time.perf_counter() - t0
    n_probes = status["cluster_size"] * 2
    sequential_floor = n_probes * 0.12
    # Must overlap probes; sequential would be >= sequential_floor.
    assert elapsed < sequential_floor * 0.65
    assert status["cluster_size"] >= 3
    assert len(calls) == n_probes
