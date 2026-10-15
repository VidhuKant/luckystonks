#!/usr/bin/env python3
"""Entrypoint for the single trading node."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # scripts/ → repo root; cli.py → parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
    
def main() -> None:

    from luckystonks.env_loader import load_project_env
    load_project_env()
    from luckystonks.node.server import serve

    serve()


if __name__ == "__main__":
    main()
