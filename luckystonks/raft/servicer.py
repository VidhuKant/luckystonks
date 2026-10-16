from __future__ import annotations

from luckystonks.pb import raft_pb2, raft_pb2_grpc

from .log_entry import LogEntry
from .runtime import RaftRuntime


class RaftGrpcServicer(raft_pb2_grpc.RaftServicer):
    def __init__(self, runtime: RaftRuntime) -> None:
        self.runtime = runtime

    def RequestVote(self, request, context):
        with self.runtime.lock:
            reply = self.runtime.node.handle_request_vote(
                from_peer=int(getattr(request, "from")),
                to_peer=int(request.to),
                term=int(request.term),
                last_log_index=int(request.last_log_index),
                last_log_term=int(request.last_log_term),
            )
        return raft_pb2.RequestVoteReply(
            **{
                "from": int(reply["from"]),
                "to": int(reply["to"]),
                "term": int(reply["term"]),
                "vote_granted": bool(reply["vote_granted"]),
            }
        )

    def AppendEntries(self, request, context):
        entries = [LogEntry(int(e.term), bytes(e.command)) for e in request.entries]
        with self.runtime.lock:
            reply = self.runtime.node.handle_append_entries(
                from_peer=int(getattr(request, "from")),
                to_peer=int(request.to),
                term=int(request.term),
                prev_index=int(request.prev_index),
                prev_term=int(request.prev_term),
                leader_commit=int(request.commit_index),
                entries=entries,
            )
            self.runtime.reset_election_timer()
            if reply["entry_appended"] or len(entries) == 0:
                self.runtime.note_leader(int(getattr(request, "from")))
        return raft_pb2.AppendEntriesReply(
            **{
                "from": int(reply["from"]),
                "to": int(reply["to"]),
                "term": int(reply["term"]),
                "entry_appended": bool(reply["entry_appended"]),
                "match_index": int(reply["match_index"]),
            }
        )
