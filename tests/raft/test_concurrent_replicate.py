from concurrent.futures import ThreadPoolExecutor, as_completed

from luckystonks.matching.models import Command
from luckystonks.raft.cluster_state import engine_fingerprint
from luckystonks.raft.in_memory import InMemoryCluster


def test_concurrent_replicate_commands_on_leader() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(0) == 0

    def submit(i: int) -> bool:
        cmd = Command(f"conc-{i}", "pratham", "BUY", "WIPRO", 500 + (i % 50), 1)
        return cluster.replicate_command(0, cmd)

    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(submit, range(120)))

    assert all(results)
    fps = {engine_fingerprint(n.engine) for n in cluster.nodes.values()}
    assert len(fps) == 1
    assert len(cluster.nodes[0].engine.order_log) == 120
