from __future__ import annotations
import json
from luckystonks.matching.models import Command

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

def decode_command(data: bytes)-> Command:
    payload = json.loads(data.decode("utf-8"))
    return Command(
        client_request_id=str(payload["client_request_id"]),
        user_id=str(payload["user_id"]),
        side=payload["side"],
        symbol=str(payload["symbol"]),
        price=int(payload["price"]),
        qty=int(payload["qty"]),
    )