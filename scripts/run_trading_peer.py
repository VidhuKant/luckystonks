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
    from luckystonks.cluster_size import (
        cluster_size,
        raft_peers_env,
        raft_port,
        trading_peers_env,
        trading_port,
    )

    size = cluster_size()
    if peer_id < 0 or peer_id >= size:
        print(
            f"peer_id must be in 0..{size - 1} for CLUSTER_SIZE={size}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    # Peer identity/ports must always follow argv — never setdefault. A parent
    # shell with RAFT_PEER_ID=0 (or LUCKYSTONKS_PORT) would otherwise launch
    # every demo peer as peer 0 on the same ports.
    os.environ["RAFT_ENABLED"] = "1"
    os.environ["RAFT_PEER_ID"] = str(peer_id)
    os.environ["LUCKYSTONKS_PORT"] = str(trading_port(peer_id))
    os.environ["RAFT_PORT"] = str(raft_port(peer_id))
    os.environ.setdefault("RAFT_HOST", "127.0.0.1")
    os.environ.setdefault("TRADING_HOST", "127.0.0.1")
    os.environ["RAFT_PEERS"] = raft_peers_env(os.environ["RAFT_HOST"], size)
    os.environ["TRADING_PEERS"] = trading_peers_env(os.environ["TRADING_HOST"], size)
    os.environ["LUCKYSTONKS_STATE_FILE"] = str(
        _ROOT / "data" / "runtime" / f"state-peer{peer_id}.json"
    )
    os.environ["RAFT_STATE_FILE"] = str(
        _ROOT / "data" / "runtime" / f"raft-peer{peer_id}.json"
    )

    from luckystonks.env_loader import load_project_env

    load_project_env()
    from luckystonks.node.server import serve

    serve()


if __name__ == "__main__":
    main()
