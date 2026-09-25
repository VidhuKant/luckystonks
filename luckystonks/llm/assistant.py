from typing import Any

# Insight gRPC (this process)
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 50070

# Trading tape source (gRPC Get TRADES)
TRADING_ADDR = "localhost:50051"

# External vLLM (OpenAI-compatible HTTP) — comment/target only; not used in skeleton
INFER_BASE_URL = "http://127.0.0.1:8000/v1"
INFER_MODEL = ""


class InsightServicer:
    def GetInsight(self, request: Any, context: Any) -> Any:
        raise NotImplementedError


def fetch_tape(trading_stub: Any) -> list[Any]:
    raise NotImplementedError


def complete_chat(messages: list[dict], model: str | None = None) -> str:
    raise NotImplementedError


def template_summary(tape: list[Any], query: str, context: str) -> str:
    raise NotImplementedError


def summarize(tape: list[Any], query: str, context: str) -> str:
    raise NotImplementedError


def serve() -> None:
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError
