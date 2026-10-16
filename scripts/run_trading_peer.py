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
    os.environ.setdefault(
        "RAFT_PEERS",
        "0:60051,1:60052,2:60053",
    )
    os.environ.setdefault(
        "TRADING_PEERS",
        "0:50051,1:50052,2:50053",
    )
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
