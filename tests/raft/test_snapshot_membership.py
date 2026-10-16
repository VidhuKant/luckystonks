from luckystonks.matching.models import Command
from luckystonks.raft.cluster_state import engine_fingerprint
from luckystonks.raft.in_memory import InMemoryCluster
from luckystonks.raft.persist import load_raft_state, save_raft_state
from luckystonks.raft.snapshot import compact_through_applied


def test_log_compaction_keeps_state_and_shortens_log() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    for node in cluster.nodes.values():
        node.compact_threshold = 2
    assert cluster.run_election(0) == 0

    for i in range(5):
        cmd = Command(f"cmp-{i}", "ved", "SELL", "RELIANCE", 4000 + i, 1)
        assert cluster.replicate_command(0, cmd)

    leader = cluster.nodes[0]
    assert leader.snapshot_last_included_index > 0
    assert len(leader.log) < 5
    fps = {engine_fingerprint(n.engine) for n in cluster.nodes.values()}
    assert len(fps) == 1


def test_install_snapshot_brings_late_follower_current() -> None:
    cluster = InMemoryCluster([0, 1])
    cluster.seed_all()
    assert cluster.run_election(0) == 0
    for i in range(4):
        cmd = Command(f"snap-{i}", "ved", "SELL", "RELIANCE", 3000 + i, 1)
        assert cluster.replicate_command(0, cmd)

    leader = cluster.nodes[0]
    compact_through_applied(leader)
    late = cluster.nodes[1]
    late.engine.seed_demo_users()
    late.log.clear()
    late.snapshot_last_included_index = 0
    late.snapshot_data = None
    late.last_applied = 0
    late.commit_index = 0

    assert leader.snapshot_data is not None
    late.handle_install_snapshot(
        from_peer=0,
        to_peer=1,
        term=leader.current_term,
        last_included_index=leader.snapshot_last_included_index,
        last_included_term=leader.snapshot_last_included_term,
        data=leader.snapshot_data,
    )
    assert late.last_applied == leader.snapshot_last_included_index
    assert engine_fingerprint(late.engine) == engine_fingerprint(leader.engine)


def test_snapshot_persist_round_trip(tmp_path) -> None:
    cluster = InMemoryCluster([0])
    cluster.seed_all()
    leader = cluster.nodes[0]
    leader.compact_threshold = 1
    leader.leader_propose(Command("p1", "ved", "SELL", "RELIANCE", 2450, 10), term=1)
    leader.leader_propose(Command("p2", "pratham", "BUY", "RELIANCE", 2450, 10), term=1)
    path = tmp_path / "raft.json"
    leader.raft_state_path = path
    save_raft_state(path, leader)

    from luckystonks.matching.engine import Engine
    from luckystonks.raft.node import RaftNode

    engine = Engine()
    engine.seed_demo_users()
    restored = RaftNode(0, engine)
    load_raft_state(path, restored)
    restored.last_applied = restored.snapshot_last_included_index
    while restored.last_applied < restored.commit_index:
        restored._apply_committed()
    assert restored.snapshot_last_included_index > 0
    assert len(restored.engine.order_log) >= 1


def test_add_and_remove_cluster_member_via_log() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(0) == 0
    assert cluster.replicate_config_change(
        0, "add", 3, "127.0.0.1:60054", "127.0.0.1:50054"
    )
    assert 3 in cluster.registry.peer_ids()
    assert 3 in cluster.nodes

    assert cluster.replicate_config_change(0, "remove", 2, "", "")
    assert 2 not in cluster.registry.peer_ids()
    assert 2 not in cluster.nodes

    cmd = Command("after-remove", "ved", "SELL", "RELIANCE", 2450, 5)
    assert cluster.replicate_command(0, cmd)
