from pathlib import Path

from luckystonks.matching.models import Command
from luckystonks.raft.cluster_state import engine_fingerprint
from luckystonks.raft.in_memory import InMemoryCluster


def test_cluster_order_and_admin_reset_keep_peers_aligned(tmp_path: Path) -> None:
    seed = tmp_path / "seed.json"
    seed.write_text(
        (
            Path(__file__).resolve().parents[2] / "data" / "seed_users.json"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(0) == 0

    cmd = Command("r1", "ved", "SELL", "RELIANCE", 2450, 10)
    assert cluster.replicate_command(0, cmd)
    fps = {engine_fingerprint(n.engine) for n in cluster.nodes.values()}
    assert len(fps) == 1

    cmd2 = Command("r2", "pratham", "BUY", "RELIANCE", 2450, 10)
    assert cluster.replicate_command(0, cmd2)
    fps = {engine_fingerprint(n.engine) for n in cluster.nodes.values()}
    assert len(fps) == 1
    for node in cluster.nodes.values():
        assert len(node.engine.trades) == 1

    assert cluster.replicate_admin_reset(0, str(seed))
    fps = {engine_fingerprint(n.engine) for n in cluster.nodes.values()}
    assert len(fps) == 1
    for node in cluster.nodes.values():
        assert node.engine.trades == []
        assert node.engine.books == {}
        assert node.engine.order_log == []
        assert node.engine.users["ved"].shares.get("RELIANCE") == 15
