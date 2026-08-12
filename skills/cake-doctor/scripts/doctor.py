#!/usr/bin/env python3
"""Run a read-only health check over the configured Cake portfolio."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from cake_core import CakeDoctor, CakeError  # noqa: E402


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--without-delivery-links", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = CakeDoctor().check(
            check_delivery_links=not args.without_delivery_links
        )
        emit(result)
        return 0
    except CakeError as exc:
        emit({"status": "error", "message": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
