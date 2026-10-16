from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command
from luckystonks.raft.codec import encode_command
from luckystonks.raft.log_entry import LogEntry
from luckystonks.raft.node import RaftNode


def test_append_commit_applies_to_engine() -> None:
    engine = Engine()
    engine.seed_demo_users()
    node = RaftNode(0, engine)

    cmd = Command("r1", "ved", "SELL", "RELIANCE", 2450, 10)
    reply = node.leader_propose(cmd, term=1)

    assert reply["entry_appended"] is True
    assert node.commit_index == 1
    assert node.last_applied == 1
    assert len(engine.books["RELIANCE"].asks) == 1
    assert len(engine.order_log) == 1


def test_reject_append_when_prev_term_mismatch() -> None:
    engine = Engine()
    engine.seed_demo_users()
    node = RaftNode(0, engine)
    node.log.append(LogEntry(1, encode_command(Command("a", "ved", "SELL", "RELIANCE", 2450, 1))))

    reply = node.handle_append_entries(
        from_peer=1,
        to_peer=0,
        term=1,
        prev_index=1,
        prev_term=99,
        leader_commit=2,
        entries=[LogEntry(1, encode_command(Command("b", "ved", "SELL", "RELIANCE", 2450, 1)))],
    )

    assert reply["entry_appended"] is False
    assert len(node.log) == 1


def test_truncate_conflicting_suffix_then_apply() -> None:
    engine = Engine()
    engine.seed_demo_users()
    node = RaftNode(0, engine)
    c1 = Command("r1", "ved", "SELL", "RELIANCE", 2450, 10)
    c2 = Command("r2", "pratham", "BUY", "RELIANCE", 2450, 10)
    node.leader_propose(c1, term=1)
    assert len(engine.books["RELIANCE"].asks) == 1

    node.log.append(LogEntry(1, encode_command(c2)))
    node.commit_index = 2
    node._apply_committed()
    assert len(engine.trades) == 1

    node2 = RaftNode(1, Engine())
    node2.engine.seed_demo_users()
    sync = node2.handle_append_entries(
        from_peer=0,
        to_peer=1,
        term=1,
        prev_index=0,
        prev_term=0,
        leader_commit=1,
        entries=[LogEntry(1, encode_command(c1))],
    )
    assert sync["entry_appended"] is True
    node2.log.append(
        LogEntry(1, encode_command(Command("stale", "ved", "SELL", "RELIANCE", 2400, 5)))
    )
    reply = node2.handle_append_entries(
        from_peer=0,
        to_peer=1,
        term=2,
        prev_index=1,
        prev_term=1,
        leader_commit=2,
        entries=[LogEntry(2, encode_command(c2))],
    )
    assert reply["entry_appended"] is True
    assert len(node2.log) == 2
    assert len(node2.engine.trades) == 1