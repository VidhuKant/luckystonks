from __future__ import annotations

import json
from collections.abc import Callable

from luckystonks.matching.engine import Engine
from luckystonks.matching.models import Command

ADMIN_RESET_KIND = "ADMIN_RESET"
CONFIG_CHANGE_KIND = "CONFIG_CHANGE"


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


def encode_config_change(action: str, peer_id: int, raft_addr: str, trading_addr: str) -> bytes:
    payload = {
        "kind": CONFIG_CHANGE_KIND,
        "action": action,
        "peer_id": int(peer_id),
        "raft_addr": raft_addr,
        "trading_addr": trading_addr,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def decode_config_change(data: bytes) -> dict[str, str | int]:
    payload = json.loads(data.decode("utf-8"))
    if payload.get("kind") != CONFIG_CHANGE_KIND:
        raise ValueError("not a config change entry")
    return payload


def apply_log_entry(
    engine: Engine,
    data: bytes,
    admin_reset_hooks: list[Callable[[], None]] | None = None,
    config_change_hooks: list[Callable[[dict[str, str | int]], None]] | None = None,
) -> None:
    payload = json.loads(data.decode("utf-8"))
    kind = payload.get("kind")
    if kind == ADMIN_RESET_KIND:
        engine.reset_from_seed(str(payload["seed_path"]))
        for hook in admin_reset_hooks or []:
            hook()
        return
    if kind == CONFIG_CHANGE_KIND:
        for hook in config_change_hooks or []:
            hook(payload)
        return
    engine.apply(decode_command(data))