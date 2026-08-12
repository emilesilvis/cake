#!/usr/bin/env python3
"""Read, preview, and explicitly apply one canonical Cake Slice definition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from cake_core import CakeError, CakeSlicer  # noqa: E402


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def add_draft(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--success", required=True)
    parser.add_argument("--not-included")
    parser.add_argument("--github-issue")
    parser.add_argument("--apply-token")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_cake = subparsers.add_parser("read-cake")
    read_cake.add_argument("--cake", required=True)

    read_slice = subparsers.add_parser("read-slice")
    read_slice.add_argument("--cake", required=True)
    read_slice.add_argument("--slice", required=True, dest="slice_reference")

    create = subparsers.add_parser("create")
    create.add_argument("--cake", required=True)
    add_draft(create)

    update = subparsers.add_parser("update")
    update.add_argument("--cake", required=True)
    update.add_argument("--slice", required=True, dest="slice_reference")
    add_draft(update)

    adopt = subparsers.add_parser("adopt")
    adopt.add_argument("--cake", required=True)
    adopt.add_argument("--slice", required=True, dest="slice_reference")
    add_draft(adopt)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    slicer = CakeSlicer()
    try:
        if args.command == "read-cake":
            result = slicer.read_cake(args.cake)
        elif args.command == "read-slice":
            result = slicer.read_slice(args.cake, args.slice_reference)
        else:
            values = {
                "title": args.title,
                "outcome": args.outcome,
                "success": args.success,
                "not_included": args.not_included,
                "github_issue": args.github_issue,
                "confirmation_token": args.apply_token,
            }
            if args.command == "create":
                result = slicer.create(args.cake, **values)
            elif args.command == "adopt":
                result = slicer.adopt(args.cake, args.slice_reference, **values)
            else:
                result = slicer.update(args.cake, args.slice_reference, **values)
        emit(result)
        return 0
    except CakeError as exc:
        emit({"status": "error", "message": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
