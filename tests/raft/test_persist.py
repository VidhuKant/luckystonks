from pathlib import Path

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command
from luckystonks.raft.node import RaftNode
from luckystonks.raft.persist import load_raft_state, save_raft_state


def test_raft_state_save_load_and_replay(tmp_path: Path) -> None:
    raft_file = tmp_path / "raft.json"
    engine = Engine()
    engine.seed_demo_users()
    node = RaftNode(0, engine)
    node.raft_state_path = raft_file
    node.leader_propose(Command("r1", "ved", "SELL", "RELIANCE", 2450, 10), term=1)
    assert raft_file.is_file()

    engine2 = Engine()
    engine2.seed_demo_users()
    restored = RaftNode(0, engine2)
    load_raft_state(raft_file, restored)
    restored.last_applied = 0
    while restored.last_applied < restored.commit_index:
        restored._apply_committed()
    assert len(engine2.books["RELIANCE"].asks) == 1
    assert restored.commit_index == restored.last_applied
