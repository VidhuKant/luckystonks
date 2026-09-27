from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv

def load_project_env() -> None:
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env", override=False)