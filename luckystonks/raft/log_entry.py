from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class LogEntry:
    term:int
    command: bytes