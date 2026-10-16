#!/usr/bin/env python3
"""Run many CLI orders in parallel against a trading port (live cluster stress)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def one_order(port: int, index: int) -> tuple[int, bool, str]:
    price = 500 + (index % 300)
    cmd = [
        sys.executable,
        "-m",
        "luckystonks.client.cli",
        "--port",
        str(port),
        "order",
        "pratham",
        "pratham",
        "BUY",
        "WIPRO",
        str(price),
        "1",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_ROOT))
    ok = result.returncode == 0 and "RESTING" in result.stdout
    detail = (result.stdout or "") + (result.stderr or "")
    return index, ok, detail.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--workers", type=int, default=40)
    args = parser.parse_args()

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(one_order, args.port, i) for i in range(args.count)]
        for fut in as_completed(futures):
            idx, ok, detail = fut.result()
            if not ok:
                failures.append(f"order {idx}: {detail[:200]}")

    print(json.dumps({"total": args.count, "failed": len(failures)}, indent=2))
    if failures:
        print("\n".join(failures[:20]), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
