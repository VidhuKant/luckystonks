from __future__ import annotations

import json
from collections.abc import Callable

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command

ADMIN_RESET_KIND = "ADMIN_RESET"


def encode_command(command: Command) -> bytes:
    payload = {
        "client_request_id": command.client_request_id,
        "user_id": command.user_id,
        "side": command.side,
        "symbol": command.symbol,
        "price": command.price,
        "qty": command.qty,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")

def decode_command(data: bytes) -> Command:
    payload = json.loads(data.decode("utf-8"))
    return Command(
        client_request_id=str(payload["client_request_id"]),
        user_id=str(payload["user_id"]),
        side=payload["side"],
        symbol=str(payload["symbol"]),
        price=int(payload["price"]),
        qty=int(payload["qty"]),
    )


def encode_admin_reset(seed_path: str) -> bytes:
    payload = {"kind": ADMIN_RESET_KIND, "seed_path": seed_path}
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def apply_log_entry(
    engine: Engine,
    data: bytes,
    admin_reset_hooks: list[Callable[[], None]] | None = None,
) -> None:
    payload = json.loads(data.decode("utf-8"))
    if payload.get("kind") == ADMIN_RESET_KIND:
        engine.reset_from_seed(str(payload["seed_path"]))
        for hook in admin_reset_hooks or []:
            hook()
        return
    engine.apply(decode_command(data))