#!/usr/bin/env python3
"""Build a read-only Trello portfolio snapshot for Cake prioritisation."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from typing import Any


COMMON_PATH = Path(__file__).resolve().parents[2] / "cake-slice" / "scripts" / "cake_trello.py"
SPEC = importlib.util.spec_from_file_location("cake_trello_common", COMMON_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load Cake Trello helper at {COMMON_PATH}")
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)


CAPACITY_LISTS = {"tasks", "fixed time slots/habit"}
EXCLUDED_LISTS = {"done", "failed/parked", "failed-parked"}


def normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def portfolio_config() -> dict[str, Any]:
    return dict(common.load_config().get("portfolio", {}))


def config_status() -> dict[str, Any]:
    value = portfolio_config()
    missing = [
        field
        for field in ("projects_board", "backlog_board")
        if not value.get(field)
    ]
    return {
        "config_path": str(common.CONFIG_PATH),
        "portfolio": value,
        "missing": missing,
        "priority_needs_confirmation": True,
    }


def config_set(args: argparse.Namespace) -> dict[str, Any]:
    config = common.load_config()
    portfolio = dict(config.get("portfolio", {}))
    updates = {
        "projects_board": args.projects_board,
        "backlog_board": args.backlog_board,
        "priority": args.priority,
    }
    supplied = {key: value.strip() for key, value in updates.items() if value and value.strip()}
    if not supplied:
        raise common.CakeError("Supply at least one portfolio configuration value")
    portfolio.update(supplied)
    config["portfolio"] = portfolio
    common.save_config(config)
    return config_status()


def find_board(name: str) -> dict[str, Any]:
    boards = common.api("GET", "/members/me/boards?fields=name,url&filter=open")
    return common.exact_named(boards, name, "board")


def compact_card(card: dict[str, Any], board: str, list_name: str) -> dict[str, Any]:
    return {
        "id": card["id"],
        "name": card.get("name", ""),
        "description": card.get("desc", ""),
        "url": card.get("url", ""),
        "board": board,
        "list": list_name,
        "due": card.get("due"),
        "due_complete": bool(card.get("dueComplete")),
        "last_activity": card.get("dateLastActivity"),
        "labels": [label.get("name") or label.get("color") for label in card.get("labels", [])],
    }


def board_snapshot(board_name: str, role: str) -> dict[str, Any]:
    board = find_board(board_name)
    lists = common.api("GET", f"/boards/{board['id']}/lists?fields=name,pos&filter=open")
    cards = common.api(
        "GET",
        f"/boards/{board['id']}/cards?fields=name,desc,url,idList,due,dueComplete,labels,dateLastActivity&filter=open",
    )
    list_by_id = {item["id"]: item["name"] for item in lists}
    candidates: list[dict[str, Any]] = []
    capacity_constraints: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    exclusion_counts: dict[tuple[str, str], int] = {}

    for raw_card in cards:
        list_name = list_by_id.get(raw_card.get("idList"), "Unknown")
        normalized_list = normalize(list_name)
        card = compact_card(raw_card, board["name"], list_name)
        if normalized_list in EXCLUDED_LISTS:
            key = (list_name, "completed or deliberately parked")
            exclusion_counts[key] = exclusion_counts.get(key, 0) + 1
            continue
        if role == "projects" and normalized_list in CAPACITY_LISTS:
            capacity_constraints.append(card)
            continue
        candidates.append(card)
        if role == "projects" and normalized_list.startswith("active"):
            active.append(card)

    exclusions = [
        {"board": board["name"], "list": list_name, "count": count, "reason": reason}
        for (list_name, reason), count in sorted(exclusion_counts.items())
    ]
    return {
        "board": {"id": board["id"], "name": board["name"], "url": board.get("url")},
        "candidates": candidates,
        "capacity_constraints": capacity_constraints,
        "active": active,
        "exclusions": exclusions,
    }


def plugin_status(projects_board_id: str) -> dict[str, Any]:
    try:
        plugins = common.api("GET", f"/boards/{projects_board_id}/plugins")
    except common.CakeError:
        return {"list_limits_plugin_present": None}
    names = [plugin.get("name", "") for plugin in plugins]
    return {"list_limits_plugin_present": any(name.casefold() == "list limits" for name in names)}


def snapshot() -> dict[str, Any]:
    config = portfolio_config()
    missing = [
        field
        for field in ("projects_board", "backlog_board")
        if not config.get(field)
    ]
    if missing:
        raise common.CakeError(
            "Portfolio configuration is incomplete; missing " + ", ".join(missing)
        )
    projects = board_snapshot(config["projects_board"], "projects")
    backlog = board_snapshot(config["backlog_board"], "backlog")
    active_count = len(projects["active"])
    return {
        "portfolio_priority": config.get("priority"),
        "priority_needs_confirmation": True,
        "candidates": projects["candidates"] + backlog["candidates"],
        "capacity_constraints": projects["capacity_constraints"],
        "active": projects["active"],
        "exclusions": projects["exclusions"] + backlog["exclusions"],
        "wip": {
            "active_count": active_count,
            "limit": None,
            "needs_current_limit": True,
            **plugin_status(projects["board"]["id"]),
        },
        "boards": {"projects": projects["board"], "backlog": backlog["board"]},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    config = subparsers.add_parser("config", help="Read or update portfolio configuration")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("get")
    set_parser = config_subparsers.add_parser("set")
    set_parser.add_argument("--projects-board")
    set_parser.add_argument("--backlog-board")
    set_parser.add_argument("--priority")
    subparsers.add_parser("snapshot", help="Read all open portfolio candidates")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "config" and args.config_command == "get":
            common.emit(config_status())
        elif args.command == "config" and args.config_command == "set":
            common.emit(config_set(args))
        elif args.command == "snapshot":
            common.emit(snapshot())
        return 0
    except common.CakeError as exc:
        common.emit({"status": "error", "message": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
