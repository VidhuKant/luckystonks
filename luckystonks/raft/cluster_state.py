from __future__ import annotations

import hashlib
import json

from luckystonks.matching.engine import Engine


def engine_fingerprint(engine: Engine) -> str:
    payload = {
        "users": {
            uid: {"cash": u.cash, "shares": dict(u.shares)} for uid, u in sorted(engine.users.items())
        },
        "trade_count": len(engine.trades),
        "order_log_len": len(engine.order_log),
        "books": {
            symbol: {
                "bids": len(book.bids),
                "asks": len(book.asks),
            }
            for symbol, book in sorted(engine.books.items())
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
