#!/usr/bin/env python3
"""Entrypoint for the single trading node."""

from __future__ import annotations


def main() -> None:
    from luckystonks.node.server import serve

    serve()


if __name__ == "__main__":
    main()
