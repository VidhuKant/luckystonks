from __future__ import annotations

from luckystonks.pb import raft_pb2, raft_pb2_grpc

from .log_entry import LogEntry
from .log_util import raft_logger
from .runtime import RaftRuntime


class RaftGrpcServicer(raft_pb2_grpc.RaftServicer):
    def __init__(self, runtime: RaftRuntime) -> None:
        self.runtime = runtime
        self.log = raft_logger(runtime.node.peer_id)

    def RequestVote(self, request, context):
        from_peer = int(getattr(request, "from"))
        with self.runtime.lock:
            reply = self.runtime.node.handle_request_vote(
                from_peer=from_peer,
                to_peer=int(request.to),
                term=int(request.term),
                last_log_index=int(request.last_log_index),
                last_log_term=int(request.last_log_term),
            )
        self.log.debug(
            "rpc RequestVote from=%s term=%s granted=%s",
            from_peer,
            request.term,
            reply["vote_granted"],
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
        from_peer = int(getattr(request, "from"))
        entries = [LogEntry(int(e.term), bytes(e.command)) for e in request.entries]
        with self.runtime.lock:
            reply = self.runtime.node.handle_append_entries(
                from_peer=from_peer,
                to_peer=int(request.to),
                term=int(request.term),
                prev_index=int(request.prev_index),
                prev_term=int(request.prev_term),
                leader_commit=int(request.commit_index),
                entries=entries,
            )
            self.runtime.reset_election_timer()
            if reply["entry_appended"] or len(entries) == 0:
                self.runtime.note_leader(from_peer)
        if entries:
            self.log.info(
                "rpc AppendEntries from=%s term=%s entries=%s ok=%s match=%s",
                from_peer,
                request.term,
                len(entries),
                reply["entry_appended"],
                reply["match_index"],
            )
        else:
            self.log.debug(
                "rpc AppendEntries heartbeat from=%s term=%s ok=%s",
                from_peer,
                request.term,
                reply["entry_appended"],
            )
        return raft_pb2.AppendEntriesReply(
            **{
                "from": int(reply["from"]),
                "to": int(reply["to"]),
                "term": int(reply["term"]),
                "entry_appended": bool(reply["entry_appended"]),
                "match_index": int(reply["match_index"]),
            }
        )

    def InstallSnapshot(self, request, context):
        from_peer = int(getattr(request, "from"))
        with self.runtime.lock:
            reply = self.runtime.node.handle_install_snapshot(
                from_peer=from_peer,
                to_peer=int(request.to),
                term=int(request.term),
                last_included_index=int(request.last_included_index),
                last_included_term=int(request.last_included_term),
                data=bytes(request.data),
            )
            self.runtime.reset_election_timer()
            self.runtime.note_leader(from_peer)
        self.log.info(
            "rpc InstallSnapshot from=%s through=%s term=%s",
            from_peer,
            request.last_included_index,
            request.term,
        )
        return raft_pb2.InstallSnapshotReply(
            **{
                "from": int(reply["from"]),
                "to": int(reply["to"]),
                "term": int(reply["term"]),
            }
        )
