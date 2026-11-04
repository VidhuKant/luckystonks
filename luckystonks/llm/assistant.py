from __future__ import annotations

import json
import os
from concurrent import futures
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import grpc

from luckystonks.pb import llm_pb2, llm_pb2_grpc, trading_pb2, trading_pb2_grpc

DEFAULT_HOST = os.getenv("LUCKYSTONKS_INSIGHT_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("LUCKYSTONKS_INSIGHT_PORT", "50070"))

TRADING_ADDR = os.getenv("LUCKYSTONKS_TRADING_ADDR", "127.0.0.1:50051")
TRADING_READ_TOKEN = os.getenv("LUCKYSTONKS_TRADING_READ_TOKEN", "")

INFER_BASE_URL = os.getenv("LUCKYSTONKS_VLLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
INFER_MODEL = os.getenv("LUCKYSTONKS_VLLM_MODEL", "")
HTTP_TIMEOUT_SECONDS = float(os.getenv("LUCKYSTONKS_VLLM_TIMEOUT_SECONDS", "30"))
MAX_TAPE_ITEMS = 50


class InsightServicer(llm_pb2_grpc.InsightServicer):
    """Implementation of the Insight gRPC service."""

    def GetInsight(self, request: Any, context: grpc.ServicerContext) -> Any:
        """Return an insight response for a client query."""
        query = request.query.strip()
        if not query:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "query must not be empty")

        try:
            with grpc.insecure_channel(TRADING_ADDR) as channel:
                tape = fetch_tape(trading_pb2_grpc.TradingStub(channel))
        except Exception:
            tape = []

        return llm_pb2.GetInsightReply(
            request_id=request.request_id,
            answer=summarize(tape, query, request.context),
        )


def fetch_tape(trading_stub: Any) -> list[Any]:
    """Retrieve and decode the current trade tape."""
    reply = trading_stub.Get(
        trading_pb2.GetRequest(token=TRADING_READ_TOKEN, type="TRADES", params=""),
        timeout=5,
    )
    if reply.status != "OK":
        raise RuntimeError(f"trading tape request failed: {reply.status}")

    tape: list[Any] = []
    for item in reply.items[-MAX_TAPE_ITEMS:]:
        try:
            decoded = json.loads(item.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid trade-tape item {item.id!r}") from error
        tape.append(decoded)
    return tape


def complete_chat(messages: list[dict[str, Any]], model: str | None = None) -> str:
    """Request a chat completion from the configured vLLM endpoint."""
    chosen_model = model or INFER_MODEL
    if not chosen_model:
        raise RuntimeError("no vLLM model configured; set LUCKYSTONKS_VLLM_MODEL")

    payload = json.dumps(
        {"model": chosen_model, "messages": messages, "temperature": 0.2, "max_tokens": 350}
    ).encode("utf-8")
    request = Request(
        f"{INFER_BASE_URL}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"local vLLM request failed: {error}") from error

    try:
        answer = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("local vLLM returned an unexpected response") from error
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("local vLLM returned an empty answer")
    return answer.strip()


def _parse_context(context: str) -> dict[str, Any]:
    if not context or not str(context).strip():
        return {}
    try:
        raw = json.loads(context)
    except (TypeError, json.JSONDecodeError):
        return {"raw_context": str(context)}
    return raw if isinstance(raw, dict) else {"raw_context": raw}


def _format_portfolio(portfolio: Any) -> str:
    if not isinstance(portfolio, dict):
        return str(portfolio)
    cash = portfolio.get("cash", "unknown")
    shares = portfolio.get("shares") or {}
    if isinstance(shares, dict) and shares:
        holdings = ", ".join(f"{sym}={qty}" for sym, qty in sorted(shares.items()))
    else:
        holdings = "none"
    return f"cash={cash}; holdings: {holdings}"


def _other_user_mentioned(query: str, viewer_id: str, ctx: dict[str, Any]) -> str | None:
    """Return another user_id referenced in the query, if any."""
    q = query.lower()
    candidates: set[str] = set()
    for key in ("user_id",):
        uid = ctx.get(key)
        if isinstance(uid, str) and uid:
            candidates.add(uid)
    for row in ctx.get("all_portfolios") or []:
        if isinstance(row, dict) and isinstance(row.get("user_id"), str):
            candidates.add(row["user_id"])
    # Common seed accounts even if all_portfolios is absent.
    candidates.update({"ved", "pratham", "vidhu", "admin"})
    for uid in sorted(candidates, key=len, reverse=True):
        if uid == viewer_id:
            continue
        if uid.lower() in q:
            return uid
    return None


def _portfolio_fallback(query: str, ctx: dict[str, Any]) -> str | None:
    """Deterministic portfolio / ACL answers when vLLM is unavailable."""
    if not ctx:
        return None
    q = query.lower()
    portfolio_words = (
        "portfolio",
        "cash",
        "holding",
        "holdings",
        "shares",
        "balance",
        "my account",
        "open order",
        "resting",
    )
    if not any(w in q for w in portfolio_words):
        # Still handle explicit "X's portfolio" style asks.
        if "portfolio" not in q and not _other_user_mentioned(query, str(ctx.get("user_id") or ""), ctx):
            return None

    viewer = str(ctx.get("user_id") or "")
    role = str(ctx.get("role") or "user")
    other = _other_user_mentioned(query, viewer, ctx)
    if other:
        if role == "admin":
            for row in ctx.get("all_portfolios") or []:
                if isinstance(row, dict) and row.get("user_id") == other:
                    return (
                        f"Admin view of {other}'s portfolio: {_format_portfolio(row)}. "
                        f"Question: {query}"
                    )
            return (
                f"Admin role is active, but no portfolio for '{other}' is in context. "
                f"Question: {query}"
            )
        return (
            f"Access denied: you are logged in as '{viewer}' and cannot view "
            f"another user's portfolio ('{other}'). Question: {query}"
        )

    if not any(w in q for w in portfolio_words):
        return None

    parts: list[str] = []
    if ctx.get("portfolio") is not None:
        parts.append(f"Your portfolio ({viewer}): {_format_portfolio(ctx.get('portfolio'))}")
    elif ctx.get("portfolio_error"):
        parts.append(f"Your portfolio is unavailable ({ctx['portfolio_error']}).")
    else:
        parts.append("Your portfolio was not included in context.")

    orders = ctx.get("open_orders") or []
    if isinstance(orders, list):
        parts.append(f"Open/resting orders: {len(orders)}.")
    if role == "admin" and ctx.get("all_portfolios"):
        parts.append(
            f"Admin all-portfolios count: {len(ctx['all_portfolios'])} "
            "(ask about a specific user_id for details)."
        )
    parts.append(f"Question: {query}")
    return " ".join(parts)


def template_summary(tape: list[Any], query: str, context: str) -> str:
    """Build a deterministic response when model inference is unavailable."""
    ctx = _parse_context(context)
    portfolio_answer = _portfolio_fallback(query, ctx)
    if portfolio_answer is not None:
        return portfolio_answer

    if not tape:
        return (
            "No live trades are available right now, so I cannot summarize market activity. "
            f"Your question was: {query}"
        )

    lines = []
    for trade in tape[-5:]:
        if isinstance(trade, dict):
            symbol = trade.get("symbol", "unknown symbol")
            qty = trade.get("qty", trade.get("quantity", "unknown quantity"))
            price = trade.get("price", "unknown price")
            lines.append(f"{symbol}: {qty} shares at {price}")
        else:
            lines.append(str(trade))
    return f"Recent trades ({len(tape)} total): " + "; ".join(lines) + f". Question: {query}"


def summarize(tape: list[Any], query: str, context: str) -> str:
    """Generate an answer from the configured model or the fallback formatter."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are LuckyStonks Insight, the read-only analytics assistant for a distributed "
                "limit-order stock exchange. Answer in clear, professional language suitable for a "
                "course demonstration or operations briefing.\n\n"
                "Rules:\n"
                "- Use the trade tape JSON for market / recent-trade questions.\n"
                "- Use additional_context (JSON) for the signed-in user's portfolio and open orders "
                "when present. Never invent cash, shares, or orders.\n"
                "- Privacy: additional_context.user_id is the signed-in user. If role is not "
                "'admin', refuse requests for any other user's portfolio or balances. If role is "
                "'admin', you may use additional_context.all_portfolios when present.\n"
                "- If the tape/context lacks fields needed to answer, say so explicitly.\n"
                "- Summarize patterns when asked; keep replies concise "
                "(roughly three to eight sentences unless the user asks for more).\n"
                "- Do not provide personalized investment advice, price predictions, or buy/sell "
                "recommendations."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "trade_tape": tape[-MAX_TAPE_ITEMS:],
                    "question": query,
                    "additional_context": _parse_context(context) or context,
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        return complete_chat(messages)
    except Exception:
        return template_summary(tape, query, context)


def serve() -> None:
    """Run the Insight gRPC service."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    llm_pb2_grpc.add_InsightServicer_to_server(InsightServicer(), server)
    bound_port = server.add_insecure_port(f"{DEFAULT_HOST}:{DEFAULT_PORT}")
    if bound_port == 0:
        raise RuntimeError(f"could not bind Insight server to {DEFAULT_HOST}:{DEFAULT_PORT}")
    server.start()
    print(f"LuckyStonks Insight server running on {DEFAULT_HOST}:{bound_port}")
    server.wait_for_termination()


def main() -> None:
    """Run the Insight service entry point."""
    serve()
