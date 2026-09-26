"""Read-only Insight gRPC service backed by a local vLLM endpoint."""

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


def template_summary(tape: list[Any], query: str, _context: str) -> str:
    """Build a deterministic response when model inference is unavailable."""
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
                "You are LuckyStonks Insight, a concise market-tape assistant. "
                "Use only the supplied trade tape; state when data is missing. "
                "Do not give personalized financial advice."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"trade_tape": tape[-MAX_TAPE_ITEMS:], "question": query, "additional_context": context},
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
