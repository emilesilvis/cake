#!/usr/bin/env python3
"""Configure Cake sources and safely preview/apply portfolio transitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from cake_core import CakeError, CakePortfolio  # noqa: E402
from cake_core.config import (  # noqa: E402
    CONFIG_PATH,
    configure,
    load_config,
    save_config,
)


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def json_value(value: str, label: str) -> Any:
    text = Path(value[1:]).read_text() if value.startswith("@") else value
    try:
        return json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise CakeError(f"Could not read {label} JSON: {exc}") from None


def plan_value(value: str) -> dict[str, Any]:
    plan = json_value(value, "plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("operations"), list):
        raise CakeError("A plan must be a JSON object with an operations list")
    policies = plan.get("capacity_policies", [])
    if not isinstance(policies, list):
        raise CakeError("capacity_policies must be a JSON list")
    return {"operations": plan["operations"], "capacity_policies": policies}


def config_set(args: argparse.Namespace) -> dict[str, Any]:
    supplied = any(
        value is not None
        for value in (
            args.pantry_board,
            args.cake_stand_board,
            args.plate_board,
            args.priority,
            args.cake_stand_lists,
            args.plate_lists,
            args.capacity_sources,
        )
    )
    if not supplied:
        raise CakeError("Supply at least one configuration value")
    stand_lists = (
        json_value(args.cake_stand_lists, "Cake Stand lists")
        if args.cake_stand_lists is not None
        else None
    )
    plate_lists = (
        json_value(args.plate_lists, "Plate lists")
        if args.plate_lists is not None
        else None
    )
    capacity_sources = (
        json_value(args.capacity_sources, "capacity sources")
        if args.capacity_sources is not None
        else None
    )
    if stand_lists is not None and not isinstance(stand_lists, dict):
        raise CakeError("Cake Stand lists must be a JSON object")
    if plate_lists is not None and not isinstance(plate_lists, dict):
        raise CakeError("Plate lists must be a JSON object")
    if capacity_sources is not None and not isinstance(capacity_sources, list):
        raise CakeError("Capacity sources must be a JSON list")
    updated = configure(
        load_config(CONFIG_PATH),
        pantry_board=args.pantry_board,
        cake_stand_board=args.cake_stand_board,
        plate_board=args.plate_board,
        priority=args.priority,
        cake_stand_lists=stand_lists,
        plate_lists=plate_lists,
        capacity_sources=capacity_sources,
    )
    save_config(updated, CONFIG_PATH)
    return CakePortfolio(config=updated, config_path=CONFIG_PATH).status()


def add_plan(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--plan",
        required=True,
        help="JSON plan or @path containing operations and optional capacity_policies",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("get")
    set_parser = config_subparsers.add_parser("set")
    set_parser.add_argument("--pantry-board")
    set_parser.add_argument("--cake-stand-board")
    set_parser.add_argument("--plate-board")
    set_parser.add_argument("--priority")
    set_parser.add_argument("--cake-stand-lists")
    set_parser.add_argument("--plate-lists")
    set_parser.add_argument("--capacity-sources")

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--without-candidates", action="store_true")

    create_cake = subparsers.add_parser("create-cake")
    create_cake.add_argument("--name", required=True)
    create_cake.add_argument("--direction", required=True)
    create_cake.add_argument("--pantry-list", required=True)
    create_cake.add_argument("--finished-when")
    create_cake.add_argument("--repository")
    create_cake.add_argument("--apply-token")

    preview = subparsers.add_parser("preview")
    add_plan(preview)

    apply = subparsers.add_parser("apply")
    add_plan(apply)
    apply.add_argument("--confirmation-token", required=True)
    apply.add_argument("--allow-capacity-overage", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "config" and args.config_command == "get":
            result = CakePortfolio(config_path=CONFIG_PATH).status()
        elif args.command == "config":
            result = config_set(args)
        else:
            portfolio = CakePortfolio(config_path=CONFIG_PATH)
            if args.command == "snapshot":
                result = portfolio.snapshot(include_candidates=not args.without_candidates)
            elif args.command == "create-cake":
                result = portfolio.create_cake(
                    name=args.name,
                    direction=args.direction,
                    pantry_list=args.pantry_list,
                    finished_when=args.finished_when,
                    repository=args.repository,
                    confirmation_token=args.apply_token,
                )
            else:
                plan = plan_value(args.plan)
                if args.command == "preview":
                    result = portfolio.preview(**plan)
                else:
                    result = portfolio.apply(
                        **plan,
                        confirmation_token=args.confirmation_token,
                        allow_capacity_overage=args.allow_capacity_overage,
                    )
        emit(result)
        return 0
    except CakeError as exc:
        emit({"status": "error", "message": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
