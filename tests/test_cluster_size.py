from luckystonks.cluster_size import (
    ALLOWED_SIZES,
    cluster_size,
    peer_ids,
    quorum,
    raft_peers_env,
    trading_peers_env,
)


def test_default_cluster_size_is_five(monkeypatch) -> None:
    monkeypatch.delenv("CLUSTER_SIZE", raising=False)
    assert cluster_size() == 5
    assert peer_ids() == [0, 1, 2, 3, 4]
    assert quorum() == 3


def test_cluster_size_three(monkeypatch) -> None:
    monkeypatch.setenv("CLUSTER_SIZE", "3")
    assert cluster_size() == 3
    assert peer_ids() == [0, 1, 2]
    assert quorum() == 2
    assert "2=127.0.0.1:50053" in trading_peers_env()
    assert "2=127.0.0.1:60053" in raft_peers_env()


def test_allowed_sizes() -> None:
    assert ALLOWED_SIZES == frozenset({3, 5})
