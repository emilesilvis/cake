"""Weekly load and checklist progress for recurring Rhythms."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .domain import CakeError, normalize, parse_contract_field_line


RHYTHM_FIELDS = ("Cadence", "Load", "Supports")
MANAGED_CHECKLIST_PREFIX = "Cake · "

_DAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "once": 1,
    "two": 2,
    "twice": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_NUMBER = (
    r"(?:\d+(?:\.\d+)?|zero|one|once|two|twice|three|four|five|six|"
    r"seven|eight|nine|ten|eleven|twelve)"
)


def parse_rhythm_contract(text: str) -> dict[str, str | None]:
    """Read the small, human-facing Rhythm contract."""

    allowed = {normalize(field): field for field in RHYTHM_FIELDS}
    values: dict[str, str] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        parsed = parse_contract_field_line(raw_line)
        field = allowed.get(normalize(parsed[0])) if parsed else None
        if field:
            current = field
            values[field] = parsed[1].strip()
        elif parsed:
            current = None
        elif current and raw_line.strip():
            values[current] = f"{values[current]}\n{raw_line.rstrip()}".strip()
    return {
        "cadence": values.get("Cadence") or None,
        "load": values.get("Load") or None,
        "supports": values.get("Supports") or None,
    }


def _number(value: str) -> float:
    normalized = normalize(value)
    if normalized in _NUMBER_WORDS:
        return float(_NUMBER_WORDS[normalized])
    return float(normalized)


def _whole_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _period_kind(cadence: str, load: str) -> str | None:
    value = normalize(f"{cadence} {load}")
    if re.search(r"\b(?:per|each|every)\s+week\b|\bweekly\b", value):
        return "week"
    day_names = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    if re.search(rf"\b(?:{day_names})\b.*\b(?:{day_names})\b", value):
        return "week"
    if re.search(r"\b(?:per|each|every)\s+day\b|\bdaily\b", value):
        return "week"
    return None


def _occurrences_in_period(
    amount: float, source_period: str, target_period: str | None
) -> float:
    if source_period == "day" and target_period == "week":
        return amount * len(_DAYS)
    return amount


def _target_occurrences(
    cadence: str, load: str, period: str | None
) -> tuple[float | None, str]:
    value = normalize(load)
    match = re.search(
        rf"\b({_NUMBER})\s+times?\s+(?:per|each)\s+(day|week)\b", value
    )
    if match:
        unit = "session" if re.search(r"\bsessions?\b", value) else "occurrence"
        return _occurrences_in_period(_number(match.group(1)), match.group(2), period), unit

    nouns = r"sessions?|reviews?|logs?|days?|appointments?|bookings?|occurrences?"
    match = re.search(
        rf"\b({_NUMBER})(?:\s+[\w-]+){{0,6}}\s+({nouns})\s+(?:per|each)\s+(day|week)\b",
        value,
    )
    if match:
        noun = re.sub(r"s$", "", match.group(2))
        return _occurrences_in_period(_number(match.group(1)), match.group(3), period), noun

    cadence_value = normalize(cadence)
    match = re.search(
        rf"\b({_NUMBER})\s+times?\s+(?:per|each)\s+(day|week)\b",
        cadence_value,
    )
    if match:
        return (
            _occurrences_in_period(_number(match.group(1)), match.group(2), period),
            "occurrence",
        )
    if period == "week" and re.search(r"\bdaily\b|\bevery day\b", cadence_value):
        return 7.0, "day"
    if period == "day" or re.search(r"\bdaily\b|\bevery day\b", cadence_value):
        return 1.0, "occurrence"
    return None, "occurrence"


def _minutes_per_occurrence(load: str) -> float | None:
    value = normalize(load)
    match = re.search(rf"\b({_NUMBER})[- ](minutes?|hours?)\b", value)
    if not match:
        return None
    amount = _number(match.group(1))
    return amount * (60 if match.group(2).startswith("hour") else 1)


def quantify_rhythm_load(
    cadence: str | None, load: str | None
) -> dict[str, Any] | None:
    """Extract the conservative numeric part of a prose Rhythm contract."""

    if not cadence or not load:
        return None
    period = _period_kind(cadence, load)
    occurrences, unit = _target_occurrences(cadence, load, period)
    if not period or occurrences is None:
        return None
    minutes_per_occurrence = _minutes_per_occurrence(load)
    total_minutes = occurrences * minutes_per_occurrence if minutes_per_occurrence else None
    return {
        "period": period,
        "occurrences": _whole_number(occurrences),
        "unit": unit,
        "minutes_per_occurrence": (
            _whole_number(minutes_per_occurrence) if minutes_per_occurrence is not None else None
        ),
        "minutes": _whole_number(total_minutes) if total_minutes is not None else None,
    }


def _timezone(value: str | None):
    if value:
        offset = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
        if offset:
            minutes = (int(offset.group(2)) * 60) + int(offset.group(3))
            if offset.group(1) == "-":
                minutes *= -1
            return timezone(timedelta(minutes=minutes))
        try:
            return ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise CakeError(f"Unknown Cake timezone {value!r}") from None
    return datetime.now().astimezone().tzinfo or timezone.utc


def current_period(
    kind: str,
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> dict[str, str]:
    """Return one local daily or ISO-week period as an exclusive UTC interval."""

    if kind not in {"day", "week"}:
        raise CakeError(f"Unknown Rhythm period {kind!r}")
    tz = _timezone(timezone_name)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    local = moment.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "week":
        start -= timedelta(days=start.weekday())
        end = start + timedelta(days=7)
    else:
        end = start + timedelta(days=1)
    return {
        "kind": kind,
        "start": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "end": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "timezone": timezone_name
        or getattr(tz, "key", None)
        or local.strftime("%z")[:3] + ":" + local.strftime("%z")[3:],
    }


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, dict):
        value = value.get("dateTime") or value.get("date")
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += "T00:00:00+00:00"
    elif text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _load(amount: float, target: dict[str, Any], minutes: float | None) -> dict[str, Any]:
    return {
        "occurrences": _whole_number(max(0.0, amount)),
        "unit": target["unit"],
        "minutes": _whole_number(max(0.0, minutes)) if minutes is not None else None,
    }


def _scheduled_days(cadence: str | None) -> list[str]:
    if not cadence:
        return []
    value = normalize(cadence)
    day_by_normalized = {normalize(day): day for day in _DAYS}
    ranges = re.findall(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
        r"\s*(?:through|to|[-–—])\s*"
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        value,
    )
    selected: set[str] = set()
    if re.search(r"\bdaily\b|\bevery day\b", value):
        selected.update(_DAYS)
    for first, last in ranges:
        start = _DAYS.index(day_by_normalized[first])
        end = _DAYS.index(day_by_normalized[last])
        index = start
        while True:
            selected.add(_DAYS[index])
            if index == end:
                break
            index = (index + 1) % len(_DAYS)
    for day in _DAYS:
        if re.search(rf"\b{normalize(day)}\b", value):
            selected.add(day)
    return [day for day in _DAYS if day in selected]


def _checklist_items(contract: dict[str, str | None], target: dict[str, Any]) -> list[str]:
    occurrences = int(target["occurrences"])
    if target["period"] == "day":
        return ["Complete today's occurrence"]
    days = _scheduled_days(contract.get("cadence"))
    if len(days) == occurrences:
        return days
    return [f"Occurrence {index}" for index in range(1, occurrences + 1)]


def rhythm_checklist_spec(
    card: dict[str, Any],
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> dict[str, Any] | None:
    """Return the one managed checklist Cake expects for the current period."""

    contract = parse_rhythm_contract(str(card.get("desc") or ""))
    target = quantify_rhythm_load(contract.get("cadence"), contract.get("load"))
    if not target:
        return None
    period = current_period(target["period"], now=now, timezone_name=timezone_name)
    tz = _timezone(period["timezone"])
    start = _datetime(period["start"])
    end = _datetime(period["end"])
    assert start and end
    local_start = start.astimezone(tz).date()
    local_end = (end.astimezone(tz) - timedelta(days=1)).date()
    label = (
        local_start.isoformat()
        if target["period"] == "day"
        else f"{local_start.isoformat()}–{local_end.isoformat()}"
    )
    return {
        "name": f"{MANAGED_CHECKLIST_PREFIX}{label}",
        "period": period,
        "target": target,
        "items": _checklist_items(contract, target),
    }


def _managed_checklists(checklists: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        checklist
        for checklist in checklists
        if str(checklist.get("name") or "").startswith(MANAGED_CHECKLIST_PREFIX)
    ]


def rhythm_progress(
    card: dict[str, Any],
    checklists: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Measure completed and remaining load from the current managed checklist."""

    spec = rhythm_checklist_spec(card, now=now, timezone_name=timezone_name)
    if not spec:
        return {
            "status": "unquantified",
            "period": None,
            "target": None,
            "completed": None,
            "remaining": None,
            "checklist": None,
            "evidence": [],
        }
    values = list(checklists)
    managed = _managed_checklists(values)
    current = [item for item in managed if item.get("name") == spec["name"]]
    target = spec["target"]
    target_occurrences = float(target["occurrences"])
    if len(managed) > 1 or len(current) != 1:
        return {
            "status": "ambiguous" if len(managed) > 1 else "needs_sync",
            "period": spec["period"],
            "target": _load(
                target_occurrences,
                target,
                float(target["minutes"]) if target.get("minutes") is not None else None,
            ),
            "completed": _load(
                0, target, 0.0 if target.get("minutes") is not None else None
            ),
            "remaining": _load(
                target_occurrences,
                target,
                float(target["minutes"]) if target.get("minutes") is not None else None,
            ),
            "checklist": {"expected_name": spec["name"], "items": spec["items"]},
            "evidence": [],
        }

    checklist = current[0]
    expected = {normalize(name) for name in spec["items"]}
    actual_names = [
        normalize(str(item.get("name") or ""))
        for item in sorted(
            checklist.get("checkItems", []), key=lambda item: item.get("pos", 0)
        )
    ]
    expected_names = [normalize(name) for name in spec["items"]]
    completed_items = [
        item
        for item in checklist.get("checkItems", [])
        if normalize(str(item.get("name") or "")) in expected
        and normalize(str(item.get("state") or "")) == "complete"
    ]
    completed_count = min(target_occurrences, float(len(completed_items)))
    per_occurrence = target.get("minutes_per_occurrence")
    completed_minutes = (
        completed_count * float(per_occurrence)
        if per_occurrence is not None
        else None
    )
    remaining_minutes = (
        float(target["minutes"]) - float(completed_minutes or 0)
        if target.get("minutes") is not None
        else None
    )
    return {
        "status": "current" if actual_names == expected_names else "needs_sync",
        "period": spec["period"],
        "target": _load(
            target_occurrences,
            target,
            float(target["minutes"]) if target.get("minutes") is not None else None,
        ),
        "completed": _load(completed_count, target, completed_minutes),
        "remaining": _load(
            target_occurrences - completed_count, target, remaining_minutes
        ),
        "checklist": {
            "id": checklist.get("id"),
            "name": checklist.get("name"),
            "expected_items": spec["items"],
        },
        "evidence": [
            {
                "id": item.get("id"),
                "source": "trello_checklist",
                "title": item.get("name"),
            }
            for item in completed_items
        ],
    }


def rhythm_checklist_plan(
    card: dict[str, Any],
    checklists: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Describe exact writes needed to establish the current-period checklist."""

    spec = rhythm_checklist_spec(card, now=now, timezone_name=timezone_name)
    values = list(checklists)
    if not spec:
        return {"card": card, "status": "unquantified", "spec": None, "changes": []}
    managed = _managed_checklists(values)
    if len(managed) > 1:
        raise CakeError(
            f"Rhythm {card.get('name')!r} has more than one Cake-managed checklist"
        )
    if not managed:
        return {
            "card": card,
            "status": "needs_sync",
            "spec": spec,
            "changes": [
                {
                    "action": "create_checklist",
                    "card": card["id"],
                    "name": spec["name"],
                    "items": spec["items"],
                }
            ],
        }

    checklist = managed[0]
    rollover = checklist.get("name") != spec["name"]
    changes: list[dict[str, Any]] = []
    if rollover:
        changes.append(
            {
                "action": "rename_checklist",
                "checklist": checklist["id"],
                "from": checklist.get("name"),
                "to": spec["name"],
            }
        )
    existing = sorted(checklist.get("checkItems", []), key=lambda item: item.get("pos", 0))
    for index, name in enumerate(spec["items"]):
        if index >= len(existing):
            changes.append(
                {
                    "action": "add_check_item",
                    "checklist": checklist["id"],
                    "name": name,
                }
            )
            continue
        item = existing[index]
        new_state = (
            "incomplete"
            if rollover and normalize(str(item.get("state") or "")) == "complete"
            else item.get("state") or "incomplete"
        )
        if item.get("name") != name or new_state != item.get("state"):
            changes.append(
                {
                    "action": "update_check_item",
                    "card": card["id"],
                    "item": item["id"],
                    "from": {"name": item.get("name"), "state": item.get("state")},
                    "to": {"name": name, "state": new_state},
                }
            )
    for item in existing[len(spec["items"]) :]:
        changes.append(
            {
                "action": "delete_check_item",
                "card": card["id"],
                "item": item["id"],
                "name": item.get("name"),
            }
        )
    return {
        "card": card,
        "status": "needs_sync" if changes else "current",
        "spec": spec,
        "changes": changes,
    }


def observe_rhythms(
    cards: Iterable[dict[str, Any]],
    checklists_by_card: dict[str, list[dict[str, Any]]],
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> list[dict[str, Any]]:
    """Attach parsed contracts and current-period progress to Rhythm cards."""

    result = []
    for card in cards:
        result.append(
            {
                **card,
                **parse_rhythm_contract(str(card.get("desc") or "")),
                "progress": rhythm_progress(
                    card,
                    checklists_by_card.get(card["id"], []),
                    now=now,
                    timezone_name=timezone_name,
                ),
            }
        )
    return result
