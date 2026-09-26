from concurrent import futures
import os

import grpc

from luckystonks.matching.engine import Engine
from luckystonks.pb import trading_pb2_grpc

from .servicer import LuckyStonksServicer

HOST = "0.0.0.0"
PORT = "50051"
INSIGHT_READ_TOKEN = os.getenv("LUCKYSTONKS_TRADING_READ_TOKEN", "local-insight-read-token")
SEED_FILE = os.getenv("LUCKYSTONKS_SEED_FILE", "")

def serve(engine: Engine | None = None) -> None:
    engine = engine or Engine()
    if not engine.users:
        if SEED_FILE:
            engine.load_seed_data(SEED_FILE)
        else:
            engine.seed_demo_users()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    bound_port = server.add_insecure_port(f"{HOST}:{PORT}")
    if bound_port == 0:
        raise RuntimeError(f"could not bind Trading server to {HOST}:{PORT}")

    trading_pb2_grpc.add_TradingServicer_to_server(
        LuckyStonksServicer(engine, insight_read_token=INSIGHT_READ_TOKEN), server
    )

    server.start()

    print(f"LuckyStonks Trading server running on {HOST}:{PORT}")

    server.wait_for_termination()

if __name__ == "__main__":
    serve()
