from luckystonks.matching.engine import Engine
from luckystonks.pb import raft_pb2
from luckystonks.raft.node import RaftNode
from luckystonks.raft.peers import PeerRegistry
from luckystonks.raft.runtime import RaftRuntime
from luckystonks.raft.servicer import RaftGrpcServicer


def test_grpc_servicer_request_vote_roundtrip() -> None:
    node = RaftNode(1, Engine())
    runtime = RaftRuntime(node, PeerRegistry(1, {0: "127.0.0.1:1", 1: "127.0.0.1:2"}))
    servicer = RaftGrpcServicer(runtime)

    reply = servicer.RequestVote(
        raft_pb2.RequestVoteRequest(
            **{
                "from": 0,
                "to": 1,
                "term": 1,
                "last_log_index": 0,
                "last_log_term": 0,
            }
        ),
        None,
    )
    assert reply.vote_granted is True
    assert reply.term == 1


def test_grpc_servicer_append_resets_election_timer() -> None:
    node = RaftNode(0, Engine())
    runtime = RaftRuntime(node, PeerRegistry(0, {0: "127.0.0.1:1"}))
    before = runtime.election_deadline
    servicer = RaftGrpcServicer(runtime)
    servicer.AppendEntries(
        raft_pb2.AppendEntriesRequest(
            **{
                "from": 1,
                "to": 0,
                "term": 2,
                "prev_index": 0,
                "prev_term": 0,
                "commit_index": 0,
            }
        ),
        None,
    )
    assert runtime.election_deadline >= before
