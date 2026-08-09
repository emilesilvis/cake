#!/usr/bin/env python3
"""Deterministic Trello preview/apply and Cake destination configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib import error, parse, request


API_BASE = "https://api.trello.com/1"
CONFIG_PATH = Path.home() / ".config" / "cake" / "config.json"
CREDENTIALS_PATH = Path.home() / ".trello" / "credentials"


class CakeError(RuntimeError):
    pass


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def read_credentials() -> dict[str, str]:
    if not CREDENTIALS_PATH.exists():
        raise CakeError(f"Trello credentials are missing at {CREDENTIALS_PATH}")
    values: dict[str, str] = {}
    for raw_line in CREDENTIALS_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    if not values.get("API_KEY") or not values.get("API_TOKEN"):
        raise CakeError(f"Trello credentials at {CREDENTIALS_PATH} are incomplete")
    return values


def api(method: str, path: str, data: dict[str, str] | None = None) -> Any:
    credentials = read_credentials()
    query = parse.urlencode(
        {"key": credentials["API_KEY"], "token": credentials["API_TOKEN"]}
    )
    url = f"{API_BASE}{path}{'&' if '?' in path else '?'}{query}"
    body = parse.urlencode(data).encode() if data is not None else None
    req = request.Request(url, data=body, method=method)
    try:
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode())
    except error.HTTPError as exc:
        response_body = exc.read().decode(errors="replace")[:500]
        raise CakeError(f"Trello returned HTTP {exc.code}: {response_body}") from None
    except error.URLError as exc:
        raise CakeError(f"Could not reach Trello: {exc.reason}") from None


def card_id(value: str) -> str:
    match = re.search(r"trello\.com/c/([A-Za-z0-9]+)", value)
    return match.group(1) if match else value.strip()


def get_card(value: str) -> dict[str, Any]:
    identifier = parse.quote(card_id(value), safe="")
    return api(
        "GET",
        f"/cards/{identifier}?fields=name,desc,url,closed,idBoard,idList",
    )


def description(outcome: str, success: str, not_included: str | None) -> str:
    lines = [f"Outcome: {outcome.strip()}", f"Success: {success.strip()}"]
    if not_included and not_included.strip():
        lines.append(f"Not included: {not_included.strip()}")
    return "\n".join(lines)


def token_for(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:20]


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"version": 1, "repositories": {}}
    try:
        value = json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CakeError(f"Could not read Cake config at {CONFIG_PATH}: {exc}") from None
    if not isinstance(value, dict) or not isinstance(value.get("repositories"), dict):
        raise CakeError(f"Cake config at {CONFIG_PATH} has an invalid shape")
    return value


def save_config(value: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(CONFIG_PATH)


def git_remote(repo: str) -> str:
    path = str(Path(repo).expanduser().resolve())
    completed = subprocess.run(
        ["git", "-C", path, "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise CakeError(f"Repository {path} has no origin remote")
    return normalize_remote(completed.stdout.strip())


def normalize_remote(remote: str) -> str:
    value = remote.strip()
    value = re.sub(r"^git@([^:]+):", r"https://\1/", value)
    value = re.sub(r"^ssh://git@", "https://", value)
    value = value.removesuffix(".git").rstrip("/")
    return value.lower()


def exact_named(items: list[dict[str, Any]], name: str, kind: str) -> dict[str, Any]:
    matches = [item for item in items if item.get("name", "").casefold() == name.casefold()]
    if not matches:
        raise CakeError(f"No open Trello {kind} named {name!r} was found")
    if len(matches) > 1:
        raise CakeError(f"More than one open Trello {kind} is named {name!r}; use a unique name")
    return matches[0]


def resolve_destination(board_name: str, list_name: str) -> dict[str, str]:
    boards = api("GET", "/members/me/boards?fields=name,url&filter=open")
    board = exact_named(boards, board_name, "board")
    lists = api("GET", f"/boards/{board['id']}/lists?fields=name&filter=open")
    trello_list = exact_named(lists, list_name, "list")
    return {
        "board_id": board["id"],
        "board_name": board["name"],
        "list_id": trello_list["id"],
        "list_name": trello_list["name"],
    }


def config_get(repo: str) -> dict[str, Any]:
    remote = git_remote(repo)
    destination = load_config()["repositories"].get(remote)
    if not destination:
        raise CakeError(
            f"No Trello destination is configured for {remote}. "
            "Ask for the board and list, then run config set."
        )
    return {"remote": remote, **destination}


def config_set(repo: str, board: str, list_name: str) -> dict[str, Any]:
    remote = git_remote(repo)
    destination = resolve_destination(board, list_name)
    config = load_config()
    config["repositories"][remote] = destination
    save_config(config)
    return {"config_path": str(CONFIG_PATH), "remote": remote, **destination}


def update_payload(args: argparse.Namespace, current: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "update-card",
        "card_id": current["id"],
        "source": {"name": current.get("name", ""), "desc": current.get("desc", "")},
        "target": {
            "name": args.title.strip(),
            "desc": description(args.outcome, args.success, args.not_included),
        },
    }


def update_card(args: argparse.Namespace) -> dict[str, Any]:
    current = get_card(args.card)
    if current.get("closed"):
        raise CakeError("The Trello card is archived; Cake only updates open cards")
    payload = update_payload(args, current)
    token = token_for(payload)
    preview = {"confirmation_token": token, **payload}
    if not args.apply_token:
        return {"status": "preview", **preview}
    if args.apply_token != token:
        raise CakeError("The confirmation token is invalid or the card changed after preview")
    if payload["source"] == payload["target"]:
        return {"status": "unchanged", "card": current}
    source_text = (
        "Source direction before Cake slicing:\n"
        f"Title: {payload['source']['name']}\n"
        f"Description: {payload['source']['desc'] or '(empty)'}"
    )
    api("POST", f"/cards/{current['id']}/actions/comments", {"text": source_text})
    updated = api("PUT", f"/cards/{current['id']}", payload["target"])
    return {
        "status": "updated",
        "card": {key: updated.get(key) for key in ("id", "name", "desc", "url")},
    }


def create_payload(args: argparse.Namespace, destination: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "create-card",
        "remote": destination["remote"],
        "destination": {
            "board_id": destination["board_id"],
            "board_name": destination["board_name"],
            "list_id": destination["list_id"],
            "list_name": destination["list_name"],
        },
        "target": {
            "name": args.title.strip(),
            "desc": description(args.outcome, args.success, args.not_included),
        },
    }


def create_card(args: argparse.Namespace) -> dict[str, Any]:
    destination = config_get(args.repo)
    payload = create_payload(args, destination)
    token = token_for(payload)
    preview = {"confirmation_token": token, **payload}
    if not args.apply_token:
        return {"status": "preview", **preview}
    if args.apply_token != token:
        raise CakeError("The confirmation token is invalid or the destination changed after preview")
    created = api(
        "POST",
        "/cards",
        {
            "idList": payload["destination"]["list_id"],
            "name": payload["target"]["name"],
            "desc": payload["target"]["desc"],
            "pos": "top",
        },
    )
    return {
        "status": "created",
        "card": {key: created.get(key) for key in ("id", "name", "desc", "url")},
    }


def add_card_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--success", required=True)
    parser.add_argument("--not-included")
    parser.add_argument("--apply-token")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    read = subparsers.add_parser("read-card", help="Read one open or archived card")
    read.add_argument("card")

    config = subparsers.add_parser("config", help="Read or persist a repo destination")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    get = config_subparsers.add_parser("get")
    get.add_argument("--repo", required=True)
    set_parser = config_subparsers.add_parser("set")
    set_parser.add_argument("--repo", required=True)
    set_parser.add_argument("--board", required=True)
    set_parser.add_argument("--list", required=True, dest="list_name")

    update = subparsers.add_parser("update-card", help="Preview or apply a card update")
    update.add_argument("--card", required=True)
    add_card_fields(update)

    create = subparsers.add_parser("create-card", help="Preview or apply a new card")
    create.add_argument("--repo", required=True)
    add_card_fields(create)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "read-card":
            emit(get_card(args.card))
        elif args.command == "config" and args.config_command == "get":
            emit(config_get(args.repo))
        elif args.command == "config" and args.config_command == "set":
            emit(config_set(args.repo, args.board, args.list_name))
        elif args.command == "update-card":
            emit(update_card(args))
        elif args.command == "create-card":
            emit(create_card(args))
        return 0
    except CakeError as exc:
        emit({"status": "error", "message": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
