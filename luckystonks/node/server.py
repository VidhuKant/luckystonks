from concurrent import futures

import grpc

from luckystonks.matching.engine import Engine
from luckystonks.pb import trading_pb2_grpc

from .servicer import LuckyStonksServicer

HOST = "0.0.0.0"
PORT = "50051"

def serve():
    engine = Engine()

    engine.seed_demo_users()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    server.add_insecure_port(f"{HOST}:{PORT}")

    trading_pb2_grpc.add_TradingServicer_to_server(LuckyStonksServicer(engine), server)

    server.start()

    print(f"LuckyStonks Trading server running on {HOST}:{PORT}")

    server.wait_for_termination()

if __name__ == "__main__":
    serve()
