from luckystonks.raft.peers import parse_raft_peers


def test_parse_raft_peers_short_form() -> None:
    peers = parse_raft_peers("0:60051,1:60052", default_host="127.0.0.1")
    assert peers == {0: "127.0.0.1:60051", 1: "127.0.0.1:60052"}


def test_parse_raft_peers_full_address() -> None:
    peers = parse_raft_peers("0=10.0.0.1:7000,1=10.0.0.2:7000")
    assert peers[0] == "10.0.0.1:7000"
