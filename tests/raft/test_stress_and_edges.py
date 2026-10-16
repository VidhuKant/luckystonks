from pathlib import Path

from luckystonks.matching.models import Command
from luckystonks.raft.cluster_state import engine_fingerprint
from luckystonks.raft.codec import encode_admin_reset, encode_command
from luckystonks.raft.in_memory import InMemoryCluster
from luckystonks.raft.leader_replicate import push_commit_to_followers, replicate_entry
from luckystonks.raft.log_entry import LogEntry


def test_stress_100_resting_orders_keep_fingerprints_aligned() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(0) == 0

    for i in range(100):
        cmd = Command(f"stress-{i}", "ved", "SELL", "RELIANCE", 5000 + i, 1)
        assert cluster.replicate_command(0, cmd), f"order {i} failed"

    fps = {engine_fingerprint(n.engine) for n in cluster.nodes.values()}
    assert len(fps) == 1
    assert len(cluster.nodes[0].engine.order_log) == 100


def test_replicate_fails_when_only_leader_reachable() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(0) == 0
    leader = cluster.nodes[0]
    followers = [1, 2]
    entry = LogEntry(leader.current_term, encode_command(Command("solo", "ved", "SELL", "RELIANCE", 2450, 1)))

    def send(pid, term, prev_index, prev_term, commit, entries):
        return None

    ok = replicate_entry(leader, entry, followers, send, cluster.next_index, cluster.match_index)
    assert not ok
    assert leader.commit_index == 0
    assert leader.last_log_index() == 1


def test_lagged_follower_catches_up_via_heartbeat_sync() -> None:
    cluster = InMemoryCluster([0, 1])
    cluster.seed_all()
    assert cluster.run_election(0) == 0
    cmd = Command("c1", "ved", "SELL", "RELIANCE", 2450, 10)
    assert cluster.replicate_command(0, cmd)

    follower = cluster.nodes[1]
    follower.log = follower.log[:1]
    follower.commit_index = 1
    follower.last_applied = 1
    while follower.last_applied < follower.commit_index:
        follower._apply_committed()

    cmd2 = Command("c2", "pratham", "BUY", "RELIANCE", 2450, 10)
    assert cluster.replicate_command(0, cmd2)

    leader = cluster.nodes[0]
    followers = [1]

    def send(pid, term, prev_index, prev_term, commit, entries):
        return cluster._send_append(0, pid, term, prev_index, prev_term, commit, entries)

    push_commit_to_followers(leader, followers, send, cluster.next_index, cluster.match_index)
    assert len(follower.engine.trades) == 1
    assert engine_fingerprint(follower.engine) == engine_fingerprint(leader.engine)


def test_admin_reset_replicates_with_one_unreachable_follower() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(1) == 1
    assert cluster.replicate_command(1, Command("t1", "ved", "SELL", "RELIANCE", 2450, 10))

    seed = Path(__file__).resolve().parents[2] / "data" / "seed_users.json"
    leader = cluster.nodes[1]
    followers = [0, 2]
    entry = LogEntry(leader.current_term, encode_admin_reset(str(seed)))

    def send(pid, term, prev_index, prev_term, commit, entries):
        if pid == 2:
            return None
        return cluster._send_append(1, pid, term, prev_index, prev_term, commit, entries)

    ok = replicate_entry(leader, entry, followers, send, cluster.next_index, cluster.match_index)
    assert ok
    assert cluster.nodes[0].engine.trades == []
    assert cluster.nodes[1].engine.trades == []


def test_follower_rejects_stale_leader_term() -> None:
    cluster = InMemoryCluster([0, 1])
    cluster.seed_all()
    cluster.nodes[0].current_term = 5
    cluster.nodes[1].current_term = 5
    reply = cluster.nodes[1].handle_append_entries(
        from_peer=0,
        to_peer=1,
        term=4,
        prev_index=0,
        prev_term=0,
        leader_commit=0,
        entries=[],
    )
    assert not reply["entry_appended"]
