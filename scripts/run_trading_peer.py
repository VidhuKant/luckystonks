#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: run_trading_peer.py <peer_id>", file=sys.stderr)
        raise SystemExit(2)

    peer_id = int(sys.argv[1])
    trading_port = 50051 + peer_id
    raft_port = 60051 + peer_id
    os.environ.setdefault("RAFT_ENABLED", "1")
    os.environ.setdefault("RAFT_PEER_ID", str(peer_id))
    os.environ.setdefault("LUCKYSTONKS_PORT", str(trading_port))
    os.environ.setdefault("RAFT_PORT", str(raft_port))
    os.environ.setdefault("RAFT_HOST", "127.0.0.1")
    os.environ.setdefault("TRADING_HOST", "127.0.0.1")
    if "RAFT_PEERS" not in os.environ:
        host = os.environ["RAFT_HOST"]
        os.environ["RAFT_PEERS"] = ",".join(f"{i}={host}:{60051 + i}" for i in range(3))
    if "TRADING_PEERS" not in os.environ:
        host = os.environ["TRADING_HOST"]
        os.environ["TRADING_PEERS"] = ",".join(f"{i}={host}:{50051 + i}" for i in range(3))
    os.environ.setdefault(
        "LUCKYSTONKS_STATE_FILE",
        str(_ROOT / "data" / "runtime" / f"state-peer{peer_id}.json"),
    )
    os.environ.setdefault(
        "RAFT_STATE_FILE",
        str(_ROOT / "data" / "runtime" / f"raft-peer{peer_id}.json"),
    )

    from luckystonks.env_loader import load_project_env

    load_project_env()
    from luckystonks.node.server import serve

    serve()


if __name__ == "__main__":
    main()
