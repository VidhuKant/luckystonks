from luckystonks.matching.models import Command
from luckystonks.raft.cluster_state import engine_fingerprint
from luckystonks.raft.codec import encode_command
from luckystonks.raft.in_memory import InMemoryCluster
from luckystonks.raft.log_entry import LogEntry


def test_leader_backtracks_when_follower_log_diverges() -> None:
    cluster = InMemoryCluster([0, 1])
    cluster.seed_all()
    assert cluster.run_election(0) == 0

    c1 = Command("r1", "ved", "SELL", "RELIANCE", 2450, 10)
    assert cluster.replicate_command(0, c1)

    stale = LogEntry(1, encode_command(Command("stale", "ved", "SELL", "RELIANCE", 2400, 5)))
    cluster.nodes[1].log.append(stale)

    c2 = Command("r2", "pratham", "BUY", "RELIANCE", 2450, 10)
    assert cluster.replicate_command(0, c2)
    assert len(cluster.nodes[0].engine.trades) == 1
    assert len(cluster.nodes[1].engine.trades) == 1


def test_many_orders_keep_peer_fingerprints_aligned() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(1) == 1

    for i in range(30):
        side = "SELL" if i % 2 == 0 else "BUY"
        user = "ved" if side == "SELL" else "pratham"
        cmd = Command(f"stress-{i}", user, side, "RELIANCE", 2450 + (i % 3), 1)
        assert cluster.replicate_command(1, cmd)

    fingerprints = {engine_fingerprint(n.engine) for n in cluster.nodes.values()}
    assert len(fingerprints) == 1
