from concurrent import futures
import os
from pathlib import Path

import grpc

from luckystonks.matching.engine import Engine
from luckystonks.pb import raft_pb2_grpc, trading_pb2_grpc

from .servicer import LuckyStonksServicer

HOST = "0.0.0.0"
PORT = os.getenv("LUCKYSTONKS_PORT", "50051")
RAFT_PORT = os.getenv("RAFT_PORT", "60051")
RAFT_ENABLED = os.getenv("RAFT_ENABLED", "0") == "1"
RAFT_PEER_ID = int(os.getenv("RAFT_PEER_ID", "0"))
INSIGHT_READ_TOKEN = os.getenv("LUCKYSTONKS_TRADING_READ_TOKEN", "local-insight-read-token")
_DEFAULT_SEED = Path(__file__).resolve().parent.parent.parent / "data" / "seed_users.json"
_DEFAULT_STATE = Path(__file__).resolve().parent.parent.parent / "data" / "runtime" / "state.json"
SEED_FILE = os.getenv("LUCKYSTONKS_SEED_FILE", str(_DEFAULT_SEED))
STATE_FILE = os.getenv("LUCKYSTONKS_STATE_FILE", str(_DEFAULT_STATE))
_DEFAULT_RAFT_STATE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "runtime" / f"raft-peer{RAFT_PEER_ID}.json"
)
RAFT_STATE_FILE = os.getenv("RAFT_STATE_FILE", str(_DEFAULT_RAFT_STATE))

def serve(engine: Engine | None = None, raft_runtime=None) -> None:
    engine = engine or Engine()
    state_path = Path(STATE_FILE)
    engine.set_state_path(state_path)
    if state_path.is_file():
        engine.load_state(state_path)
    elif not engine.users:
        engine.load_seed_data(SEED_FILE)
        engine._persist()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    bound_port = server.add_insecure_port(f"{HOST}:{PORT}")
    if bound_port == 0:
        raise RuntimeError(f"could not bind Trading server to {HOST}:{PORT}")

    active_raft = raft_runtime
    servicer = LuckyStonksServicer(
        engine,
        insight_read_token=INSIGHT_READ_TOKEN,
        seed_file=SEED_FILE,
        raft_runtime=active_raft,
    )

    if RAFT_ENABLED:
        from luckystonks.raft.node import RaftNode
        from luckystonks.raft.peers import (
            PeerRegistry,
            load_raft_peers_from_env,
            load_trading_peers_from_env,
        )
        from luckystonks.raft.persist import load_raft_state
        from luckystonks.raft.runtime import RaftRuntime
        from luckystonks.raft.servicer import RaftGrpcServicer

        if active_raft is None:
            raft_addrs = load_raft_peers_from_env()
            trading_addrs = load_trading_peers_from_env(raft_addrs)
            peers = PeerRegistry(RAFT_PEER_ID, raft_addrs, trading_addrs)
            raft_node = RaftNode(RAFT_PEER_ID, engine)
            raft_path = Path(RAFT_STATE_FILE)
            raft_node.raft_state_path = raft_path
            if raft_path.is_file():
                load_raft_state(raft_path, raft_node)
                while raft_node.last_applied < raft_node.commit_index:
                    raft_node._apply_committed()
            raft_node.admin_reset_hooks.append(lambda: servicer.sessions.clear())
            active_raft = RaftRuntime(raft_node, peers)
            active_raft.start()
            servicer.raft_runtime = active_raft
        raft_bound = server.add_insecure_port(f"{HOST}:{RAFT_PORT}")
        if raft_bound == 0:
            raise RuntimeError(f"could not bind Raft server to {HOST}:{RAFT_PORT}")
        raft_pb2_grpc.add_RaftServicer_to_server(RaftGrpcServicer(active_raft), server)

    trading_pb2_grpc.add_TradingServicer_to_server(servicer, server)

    server.start()

    if RAFT_ENABLED:
        print(
            f"LuckyStonks peer {RAFT_PEER_ID} trading={HOST}:{PORT} raft={HOST}:{RAFT_PORT} role={active_raft.node.role}"
        )
    else:
        print(f"LuckyStonks Trading server running on {HOST}:{PORT}")

    server.wait_for_termination()

if __name__ == "__main__":
    serve()
