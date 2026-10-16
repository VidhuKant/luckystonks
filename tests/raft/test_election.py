from luckystonks.matching.models import Command
from luckystonks.raft.in_memory import InMemoryCluster
from luckystonks.raft.log_entry import LogEntry
from luckystonks.raft.codec import encode_command


def test_three_node_election_picks_leader() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    leader_id = cluster.run_election(0)
    assert leader_id == 0
    assert cluster.nodes[0].role == "leader"
    assert cluster.nodes[1].role == "follower"
    assert cluster.nodes[2].role == "follower"


def test_request_vote_rejects_stale_term() -> None:
    cluster = InMemoryCluster([0, 1])
    cluster.seed_all()
    cluster.nodes[1].current_term = 2
    reply = cluster.nodes[1].handle_request_vote(
        from_peer=0,
        to_peer=1,
        term=1,
        last_log_index=0,
        last_log_term=0,
    )
    assert reply["vote_granted"] is False


def test_request_vote_rejects_less_up_to_date_log() -> None:
    cluster = InMemoryCluster([0, 1])
    cluster.seed_all()
    cluster.nodes[1].log.append(
        LogEntry(1, encode_command(Command("x", "ved", "SELL", "RELIANCE", 2450, 1)))
    )
    reply = cluster.nodes[1].handle_request_vote(
        from_peer=0,
        to_peer=1,
        term=1,
        last_log_index=0,
        last_log_term=0,
    )
    assert reply["vote_granted"] is False


def test_replicate_command_on_majority_updates_all_engines() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(1) == 1

    cmd = Command("r1", "ved", "SELL", "RELIANCE", 2450, 10)
    assert cluster.replicate_command(1, cmd) is True

    for node in cluster.nodes.values():
        assert node.commit_index == 1
        assert len(node.engine.books["RELIANCE"].asks) == 1
        assert len(node.engine.order_log) == 1