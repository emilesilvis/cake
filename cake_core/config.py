"""Cake configuration with a versioned, provider-oriented shape."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any

from .domain import CakeError


CONFIG_PATH = Path(os.environ.get("CAKE_CONFIG_PATH", Path.home() / ".config" / "cake" / "config.json"))

DEFAULT_LISTS = {
    "cake_stand": {
        "on_stand": "On the stand",
        "parked": "Parked",
        "finished": "Finished",
    },
    "plate": {"eating": "Eating", "blocked": "Blocked"},
}


def empty_config() -> dict[str, Any]:
    return {
        "version": 2,
        "portfolio": {
            "priority": None,
            "pantry": None,
            "cake_stand": None,
            "plate": None,
            "capacity_sources": [],
        },
    }


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return empty_config()
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CakeError(f"Could not read Cake config at {path}: {exc}") from None
    if not isinstance(value, dict):
        raise CakeError(f"Cake config at {path} must contain a JSON object")
    return value


def normalized_config(value: dict[str, Any]) -> dict[str, Any]:
    """Return v2 configuration while reporting rather than persisting legacy mappings."""

    if value.get("version") == 2:
        result = deepcopy(value)
        portfolio = result.setdefault("portfolio", {})
        if not isinstance(portfolio, dict):
            raise CakeError("Cake config portfolio must be a JSON object")
        portfolio.setdefault("priority", None)
        portfolio.setdefault("pantry", None)
        portfolio.setdefault("cake_stand", None)
        portfolio.setdefault("plate", None)
        portfolio.setdefault("capacity_sources", [])
        if not isinstance(portfolio["capacity_sources"], list):
            raise CakeError("Cake config capacity_sources must be a JSON list")
        return result

    legacy = value.get("portfolio", {}) if isinstance(value.get("portfolio"), dict) else {}
    result = empty_config()
    result["legacy"] = {
        "detected": True,
        "backlog_board": legacy.get("backlog_board"),
        "projects_board": legacy.get("projects_board"),
        "reason": "The old Backlog/Projects model cannot be mapped safely without a Plate source.",
    }
    result["portfolio"]["priority"] = legacy.get("priority")
    return result


def save_config(value: dict[str, Any], path: Path = CONFIG_PATH) -> None:
    normalized = normalized_config(value)
    normalized.pop("legacy", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def trello_source(board: str, lists: dict[str, str] | None = None) -> dict[str, Any]:
    if not board.strip():
        raise CakeError("A Trello source needs a board name, URL, or ID")
    result: dict[str, Any] = {"adapter": "trello", "board": board.strip()}
    if lists:
        result["lists"] = deepcopy(lists)
    return result


def config_status(value: dict[str, Any], path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = normalized_config(value)
    portfolio = config["portfolio"]
    missing = [role for role in ("pantry", "cake_stand", "plate") if not portfolio.get(role)]
    return {
        "config_path": str(path),
        "config": config,
        "missing": missing,
        "ready": not missing,
        "priority_needs_confirmation": True,
    }


def configure(
    value: dict[str, Any],
    *,
    pantry_board: str | None = None,
    cake_stand_board: str | None = None,
    plate_board: str | None = None,
    priority: str | None = None,
    cake_stand_lists: dict[str, str] | None = None,
    plate_lists: dict[str, str] | None = None,
    capacity_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = normalized_config(value)
    config.pop("legacy", None)
    portfolio = config["portfolio"]
    if pantry_board:
        portfolio["pantry"] = trello_source(pantry_board)
    if cake_stand_board:
        portfolio["cake_stand"] = trello_source(
            cake_stand_board, cake_stand_lists or DEFAULT_LISTS["cake_stand"]
        )
    elif cake_stand_lists and portfolio.get("cake_stand"):
        portfolio["cake_stand"]["lists"] = deepcopy(cake_stand_lists)
    if plate_board:
        portfolio["plate"] = trello_source(plate_board, plate_lists or DEFAULT_LISTS["plate"])
    elif plate_lists and portfolio.get("plate"):
        portfolio["plate"]["lists"] = deepcopy(plate_lists)
    if priority is not None:
        portfolio["priority"] = priority.strip() or None
    if capacity_sources is not None:
        portfolio["capacity_sources"] = deepcopy(capacity_sources)
    return config
