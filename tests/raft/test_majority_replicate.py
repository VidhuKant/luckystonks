from luckystonks.matching.models import Command
from luckystonks.raft.codec import encode_command
from luckystonks.raft.in_memory import InMemoryCluster
from luckystonks.raft.leader_replicate import replicate_entry
from luckystonks.raft.log_entry import LogEntry


def test_replicate_succeeds_with_one_unreachable_follower() -> None:
    cluster = InMemoryCluster([0, 1, 2])
    cluster.seed_all()
    assert cluster.run_election(0) == 0
    leader = cluster.nodes[0]
    followers = [1, 2]
    entry = LogEntry(leader.current_term, encode_command(Command("q", "ved", "SELL", "RELIANCE", 2450, 10)))

    def send(pid, term, prev_index, prev_term, commit, entries):
        if pid == 2:
            return None
        return cluster._send_append(0, pid, term, prev_index, prev_term, commit, entries)

    ok = replicate_entry(
        leader,
        entry,
        followers,
        send,
        cluster.next_index,
        cluster.match_index,
        len(cluster.registry.peer_ids()),
    )
    assert ok
    assert leader.commit_index == 1
    assert len(leader.engine.trades) == 0
    assert leader.engine.results_by_request["q"].status == "RESTING"
