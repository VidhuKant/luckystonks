from concurrent import futures
import os
from pathlib import Path

import grpc

from luckystonks.matching.engine import Engine
from luckystonks.pb import trading_pb2_grpc

from .servicer import LuckyStonksServicer

HOST = "0.0.0.0"
PORT = "50051"
INSIGHT_READ_TOKEN = os.getenv("LUCKYSTONKS_TRADING_READ_TOKEN", "local-insight-read-token")
_DEFAULT_SEED = Path(__file__).resolve().parent.parent.parent / "data" / "seed_users.json"
_DEFAULT_STATE = Path(__file__).resolve().parent.parent.parent / "data" / "runtime" / "state.json"
SEED_FILE = os.getenv("LUCKYSTONKS_SEED_FILE", str(_DEFAULT_SEED))
STATE_FILE = os.getenv("LUCKYSTONKS_STATE_FILE", str(_DEFAULT_STATE))

def serve(engine: Engine | None = None) -> None:
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

    trading_pb2_grpc.add_TradingServicer_to_server(
        LuckyStonksServicer(engine, insight_read_token=INSIGHT_READ_TOKEN, seed_file=SEED_FILE),
        server,
    )

    server.start()

    print(f"LuckyStonks Trading server running on {HOST}:{PORT}")

    server.wait_for_termination()

if __name__ == "__main__":
    serve()
