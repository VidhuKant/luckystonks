from __future__ import annotations

import logging
import os

_CONFIGURED = False


def configure_raft_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.getenv("RAFT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [peer=%(peer)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    _CONFIGURED = True


def raft_logger(peer_id: int) -> logging.LoggerAdapter:
    base = logging.getLogger("luckystonks.raft")
    return logging.LoggerAdapter(base, {"peer": peer_id})
