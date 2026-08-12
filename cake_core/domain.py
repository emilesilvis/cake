"""Provider-independent Cake contracts, invariants, and transition previews."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Iterable


CAKE_FIELDS = ("Direction", "Finished when", "Current slices", "Next slice")
SLICE_FIELDS = (
    "Cake",
    "Outcome",
    "Success",
    "Not included",
    "GitHub issue",
    "Disposition",
    "Reason",
)
TERMINAL_SLICE_DISPOSITIONS = {"finished", "abandoned"}
TERMINAL_CANONICAL_STATES = {"finished", "abandoned", "closed"}
SLICE_DISPOSITIONS = {"candidate", "current", "paused", *TERMINAL_SLICE_DISPOSITIONS}
CAKE_STATES = {"pantry", "on_stand", "parked", "finished"}


class CakeError(RuntimeError):
    """A violated Cake contract or unsafe requested operation."""


def normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def trello_card_short_link(value: str | None) -> str | None:
    """Return a Trello card's stable short link from any normal card URL."""

    if not value:
        return None
    match = re.fullmatch(
        r"https://(?:www\.)?trello\.com/c/([A-Za-z0-9_-]+)(?:/[^\s?#]*)?"
        r"(?:\?[^\s#]*)?(?:#[^\s]*)?/?",
        value.strip(),
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def is_trello_card_url(value: str | None) -> bool:
    return trello_card_short_link(value) is not None


def trello_card_url(value: str) -> str:
    """Canonicalize a Trello card URL to its stable, clickable short URL."""

    short_link = trello_card_short_link(value)
    if not short_link:
        raise CakeError("A Cake–Slice reference must be a Trello card URL")
    return f"https://trello.com/c/{short_link}"


def canonical_ref(value: str | None) -> str | None:
    """Normalize an opaque ID or URL enough for stable equality checks."""

    if value is None:
        return None
    result = value.strip()
    if not result:
        return None
    short_link = trello_card_short_link(result)
    if short_link:
        return f"trello-card:{short_link.casefold()}"
    return result.rstrip("/").casefold()


def token_for(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:20]


def _parse_fields(text: str, allowed: Iterable[str]) -> dict[str, str]:
    allowed_by_normalized = {normalize(field): field for field in allowed}
    result: dict[str, str] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        match = re.match(r"^([^:\n]+):\s*(.*)$", raw_line)
        normalized = normalize(match.group(1)) if match else ""
        if match and normalized in allowed_by_normalized:
            current = allowed_by_normalized[normalized]
            result[current] = match.group(2).strip()
            continue
        if match:
            if current and raw_line.lstrip().startswith("- "):
                result[current] = f"{result[current]}\n{raw_line.rstrip()}".strip()
                continue
            current = None
            continue
        if current and raw_line.strip():
            result[current] = f"{result[current]}\n{raw_line.rstrip()}".strip()
    return result


def _format_fields(values: Iterable[tuple[str, str | None]]) -> str:
    lines = [f"{field}: {value.strip()}" for field, value in values if value and value.strip()]
    return "\n".join(lines)


def _parse_reference_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        line.strip().removeprefix("- ").strip()
        for line in value.splitlines()
        if line.strip().removeprefix("- ").strip()
    ]


def _format_reference_list(values: Iterable[str]) -> str | None:
    canonical: list[str] = []
    seen: set[str] = set()
    for value in values:
        reference = trello_card_url(value)
        key = canonical_ref(reference)
        if key not in seen:
            canonical.append(reference)
            assert key
            seen.add(key)
    if not canonical:
        return None
    return "\n".join((canonical[0], *(f"- {value}" for value in canonical[1:])))


def parse_cake_contract(text: str) -> dict[str, Any]:
    fields = _parse_fields(text, CAKE_FIELDS)
    return {
        "direction": fields.get("Direction") or None,
        "finished_when": fields.get("Finished when") or None,
        "current_slice_links": _parse_reference_list(fields.get("Current slices")),
        "next_slice": fields.get("Next slice") or None,
    }


def format_cake_contract(
    direction: str,
    next_slice: str | None = None,
    finished_when: str | None = None,
    current_slices: Iterable[str] | None = None,
) -> str:
    if not direction.strip():
        raise CakeError("A mature Cake needs a Direction")
    current_slice_links = _format_reference_list(current_slices or [])
    canonical_next = trello_card_url(next_slice) if next_slice else None
    if current_slice_links and canonical_next:
        raise CakeError("A Cake cannot have Current slices and a Next slice at the same time")
    return _format_fields(
        (
            ("Direction", direction),
            ("Finished when", finished_when),
            ("Current slices", current_slice_links),
            ("Next slice", canonical_next),
        )
    )


def parse_slice_contract(text: str) -> dict[str, str | None]:
    fields = _parse_fields(text, SLICE_FIELDS)
    disposition = normalize(fields.get("Disposition", "candidate")) or "candidate"
    return {
        "cake": fields.get("Cake") or None,
        "outcome": fields.get("Outcome") or None,
        "success": fields.get("Success") or None,
        "not_included": fields.get("Not included") or None,
        "github_issue": fields.get("GitHub issue") or None,
        "disposition": disposition,
        "reason": fields.get("Reason") or None,
    }


def is_github_issue_url(value: str | None) -> bool:
    if not value:
        return False
    return bool(
        re.fullmatch(
            r"https://github\.com/[^/\s]+/[^/\s]+/issues/\d+/?",
            value.strip(),
            flags=re.IGNORECASE,
        )
    )


def format_slice_contract(
    cake: str,
    outcome: str,
    success: str,
    not_included: str | None = None,
    disposition: str = "candidate",
    reason: str | None = None,
    github_issue: str | None = None,
) -> str:
    canonical_cake = trello_card_url(cake)
    if not outcome.strip():
        raise CakeError("A Slice needs one finishable Outcome")
    if not success.strip():
        raise CakeError("A Slice needs observable Success")
    normalized_disposition = normalize(disposition)
    if normalized_disposition not in SLICE_DISPOSITIONS:
        raise CakeError(f"Unknown Slice disposition {disposition!r}")
    if normalized_disposition == "abandoned" and not (reason and reason.strip()):
        raise CakeError("An Abandoned Slice needs a reason")
    if github_issue and not is_github_issue_url(github_issue):
        raise CakeError("A Slice's GitHub issue must be a GitHub issue URL")
    return _format_fields(
        (
            ("Cake", canonical_cake),
            ("Outcome", outcome),
            ("Success", success),
            ("Not included", not_included),
            ("GitHub issue", github_issue),
            ("Disposition", normalized_disposition.title()),
            ("Reason", reason),
        )
    )


def _record_matches(record: dict[str, Any], reference: str) -> bool:
    expected = canonical_ref(reference)
    candidates = (record.get("id"), record.get("url"), record.get("slice"))
    return expected is not None and expected in {canonical_ref(value) for value in candidates}


def _find(records: Iterable[dict[str, Any]], reference: str, kind: str) -> dict[str, Any]:
    matches = [record for record in records if _record_matches(record, reference)]
    if not matches:
        raise CakeError(f"No {kind} matches {reference!r}")
    if len(matches) > 1:
        raise CakeError(f"More than one {kind} matches {reference!r}")
    return matches[0]


def _cake_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    stand = snapshot.get("cake_stand", {})
    return [
        *snapshot.get("pantry", []),
        *stand.get("on_stand", []),
        *stand.get("parked", []),
        *stand.get("finished", []),
        *snapshot.get("archived_cakes", []),
    ]


def _plate_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    plate = snapshot.get("plate", {})
    return [*plate.get("eating", []), *plate.get("blocked", [])]


def _slice_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return list(snapshot.get("slice_catalog", []))


def _current_key(record: dict[str, Any]) -> str | None:
    return canonical_ref(record.get("slice") or record.get("url") or record.get("id"))


def validate_snapshot(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return structural errors and external-drift warnings without mutating state."""

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    cakes = _cake_records(snapshot)
    on_stand = snapshot.get("cake_stand", {}).get("on_stand", [])
    plate = _plate_records(snapshot)
    catalog = _slice_records(snapshot)

    current_by_cake: dict[str, list[dict[str, Any]]] = {}
    current_keys: set[str] = set()
    for current in plate:
        cake_ref = current.get("cake")
        if not cake_ref:
            errors.append({"code": "orphan_slice", "slice": current.get("url") or current.get("id")})
            continue
        parent_matches = [cake for cake in on_stand if _record_matches(cake, cake_ref)]
        if len(parent_matches) != 1:
            errors.append(
                {
                    "code": "parent_not_on_stand",
                    "slice": current.get("url") or current.get("id"),
                    "cake": cake_ref,
                }
            )
            continue
        parent_key = canonical_ref(parent_matches[0].get("url") or parent_matches[0].get("id"))
        assert parent_key
        current_by_cake.setdefault(parent_key, []).append(current)
        key = _current_key(current)
        if key in current_keys:
            errors.append({"code": "duplicate_plate_slice", "slice": key})
        elif key:
            current_keys.add(key)

        if current.get("canonical_state") in TERMINAL_CANONICAL_STATES:
            warnings.append(
                {
                    "code": "terminal_slice_on_plate",
                    "slice": current.get("slice") or current.get("url"),
                    "canonical_state": current.get("canonical_state"),
                }
            )

    for cake in on_stand:
        cake_key = canonical_ref(cake.get("url") or cake.get("id"))
        current = current_by_cake.get(cake_key or "", [])
        next_slice = cake.get("next_slice")
        stored_current = list(cake.get("current_slice_links") or [])
        expected_current: list[str] = []
        for current_slice in current:
            try:
                expected_current.append(
                    trello_card_url(current_slice.get("slice") or current_slice.get("url"))
                )
            except (CakeError, TypeError):
                errors.append(
                    {
                        "code": "invalid_current_slice_url",
                        "cake": cake.get("url") or cake.get("id"),
                        "slice": current_slice.get("slice") or current_slice.get("url"),
                    }
                )
        invalid_current_links = [
            reference for reference in stored_current if not is_trello_card_url(reference)
        ]
        if invalid_current_links:
            errors.append(
                {
                    "code": "invalid_current_slice_links",
                    "cake": cake.get("url") or cake.get("id"),
                    "slices": invalid_current_links,
                }
            )
        if [canonical_ref(value) for value in stored_current] != [
            canonical_ref(value) for value in expected_current
        ]:
            errors.append(
                {
                    "code": "current_slice_links_drift",
                    "cake": cake.get("url") or cake.get("id"),
                    "actual": stored_current,
                    "expected": expected_current,
                }
            )
        if not cake.get("direction"):
            errors.append({"code": "missing_direction", "cake": cake.get("url") or cake.get("id")})
        if not current and not next_slice:
            errors.append({"code": "waiting_without_next_slice", "cake": cake.get("url") or cake.get("id")})
        if not current and next_slice:
            if not is_trello_card_url(next_slice):
                errors.append(
                    {
                        "code": "invalid_next_slice_link",
                        "cake": cake.get("url") or cake.get("id"),
                        "slice": next_slice,
                    }
                )
            matching_next = [record for record in catalog if _record_matches(record, next_slice)]
            valid_next = len(matching_next) == 1
            if valid_next:
                candidate = matching_next[0]
                valid_next = (
                    candidate.get("adapter") == "plate"
                    and bool(candidate.get("cake"))
                    and _record_matches(cake, candidate["cake"])
                    and bool(candidate.get("outcome"))
                    and bool(candidate.get("success"))
                    and normalize(candidate.get("disposition", "candidate"))
                    not in TERMINAL_SLICE_DISPOSITIONS
                )
            if not valid_next:
                errors.append(
                    {
                        "code": "invalid_next_slice",
                        "cake": cake.get("url") or cake.get("id"),
                        "slice": next_slice,
                    }
                )
        if current and next_slice:
            errors.append({"code": "current_cake_has_queued_slice", "cake": cake.get("url") or cake.get("id")})
        if canonical_ref(next_slice) in current_keys:
            errors.append({"code": "next_slice_is_current", "cake": cake.get("url") or cake.get("id")})

    for slice_record in catalog:
        if slice_record.get("adapter") != "plate":
            errors.append(
                {
                    "code": "slice_outside_plate",
                    "slice": slice_record.get("url") or slice_record.get("id"),
                }
            )
        missing = [field for field in ("cake", "outcome", "success") if not slice_record.get(field)]
        if missing:
            errors.append(
                {
                    "code": "invalid_slice_contract",
                    "slice": slice_record.get("url") or slice_record.get("id"),
                    "missing": missing,
                }
            )
            continue
        parent_matches = [cake for cake in cakes if _record_matches(cake, slice_record["cake"])]
        if not is_trello_card_url(slice_record["cake"]):
            errors.append(
                {
                    "code": "invalid_slice_cake_link",
                    "slice": slice_record.get("url") or slice_record.get("id"),
                    "cake": slice_record["cake"],
                }
            )
        if len(parent_matches) != 1:
            errors.append(
                {
                    "code": "invalid_slice_parent",
                    "slice": slice_record.get("url") or slice_record.get("id"),
                    "cake": slice_record["cake"],
                }
            )
        github_issue = slice_record.get("github_issue")
        if github_issue and not is_github_issue_url(github_issue):
            errors.append(
                {
                    "code": "invalid_github_issue",
                    "slice": slice_record.get("url") or slice_record.get("id"),
                    "github_issue": github_issue,
                }
            )

    return {"errors": errors, "warnings": warnings}


def _move_cake(snapshot: dict[str, Any], cake: dict[str, Any], target: str) -> None:
    if target not in CAKE_STATES:
        raise CakeError(f"Unknown Cake state {target!r}")
    for collection in (
        snapshot.get("pantry", []),
        snapshot.get("cake_stand", {}).get("on_stand", []),
        snapshot.get("cake_stand", {}).get("parked", []),
        snapshot.get("cake_stand", {}).get("finished", []),
    ):
        if cake in collection:
            collection.remove(cake)
            break
    cake["state"] = target
    if target == "pantry":
        snapshot.setdefault("pantry", []).append(cake)
    else:
        snapshot.setdefault("cake_stand", {}).setdefault(target, []).append(cake)


def _candidate_for(snapshot: dict[str, Any], cake: dict[str, Any], reference: str) -> dict[str, Any]:
    candidate = _find(_slice_records(snapshot), reference, "Slice")
    if not candidate.get("cake") or not _record_matches(cake, candidate["cake"]):
        raise CakeError("The nominated Slice does not belong to this Cake")
    if not candidate.get("outcome") or not candidate.get("success"):
        raise CakeError("The nominated Slice does not satisfy the Slice contract")
    if candidate.get("adapter") != "plate":
        raise CakeError("Every canonical Slice must be a Plate card")
    if normalize(candidate.get("disposition", "candidate")) in TERMINAL_SLICE_DISPOSITIONS:
        raise CakeError("A Finished or Abandoned Slice cannot be nominated")
    return candidate


def _validate_operation(operation: dict[str, Any]) -> None:
    if not isinstance(operation, dict):
        raise CakeError("Every transition operation must be a JSON object")
    action = operation.get("action")
    schemas = {
        "nominate": ({"action", "cake", "slice"}, {"action", "cake", "slice"}),
        "pull": ({"action", "cake", "lane"}, {"action", "cake"}),
        "exit": (
            {"action", "plate_slice", "disposition", "reason", "next_slice", "cake_state"},
            {"action", "plate_slice", "disposition"},
        ),
        "move_cake": (
            {
                "action",
                "cake",
                "to",
                "direction",
                "finished_when",
                "next_slice",
            },
            {"action", "cake", "to"},
        ),
        "archive_cake": ({"action", "cake"}, {"action", "cake"}),
        "reorder": (
            {"action", "collection", "record", "position"},
            {"action", "collection", "record", "position"},
        ),
    }
    if action not in schemas:
        raise CakeError(f"Unknown transition action {action!r}")
    allowed, required = schemas[action]
    unknown = sorted(set(operation) - allowed)
    missing = sorted(field for field in required if operation.get(field) is None)
    if unknown:
        raise CakeError(f"Transition action {action!r} does not accept fields: {', '.join(unknown)}")
    if missing:
        raise CakeError(f"Transition action {action!r} is missing fields: {', '.join(missing)}")
    string_fields = allowed - {"position"}
    invalid_strings = sorted(
        field
        for field in string_fields
        if field in operation
        and operation[field] is not None
        and (not isinstance(operation[field], str) or not operation[field].strip())
    )
    if invalid_strings:
        raise CakeError(
            f"Transition action {action!r} needs non-empty text for: "
            + ", ".join(invalid_strings)
        )
    if action == "exit" and operation.get("next_slice") and operation.get("cake_state"):
        raise CakeError("Resolve the parent with either next_slice or cake_state, not both")


def _apply_operation(snapshot: dict[str, Any], operation: dict[str, Any], index: int) -> None:
    _validate_operation(operation)
    action = operation.get("action")
    cakes = _cake_records(snapshot)
    on_stand = snapshot.get("cake_stand", {}).get("on_stand", [])
    plate = _plate_records(snapshot)

    if action == "nominate":
        cake = _find(on_stand, operation["cake"], "Cake on the Cake Stand")
        candidate = _candidate_for(snapshot, cake, operation["slice"])
        candidate_reference = canonical_ref(candidate.get("url") or candidate.get("id"))
        if any(_current_key(current) == candidate_reference for current in plate):
            raise CakeError("A current Slice cannot also be Next Slice")
        cake["next_slice"] = trello_card_url(candidate.get("url") or candidate.get("id"))
        return

    if action == "pull":
        cake = _find(on_stand, operation["cake"], "Cake on the Cake Stand")
        if not cake.get("next_slice"):
            raise CakeError("Only a Cake's nominated Next Slice can be pulled")
        candidate = _candidate_for(snapshot, cake, cake["next_slice"])
        candidate_ref = trello_card_url(candidate.get("url") or candidate.get("id"))
        if any(_current_key(current) == canonical_ref(candidate_ref) for current in plate):
            raise CakeError("The nominated Slice is already on Plate")
        lane = normalize(operation.get("lane", "eating")).replace(" ", "_")
        if lane not in {"eating", "blocked"}:
            raise CakeError("A pulled Slice must enter Eating or Blocked")
        current = {
            **deepcopy(candidate),
            "id": f"planned:{index}",
            "plate_card": None,
            "cake": trello_card_url(cake.get("url") or cake.get("id")),
            "slice": candidate_ref,
            "lane": lane,
            "canonical_on_plate": True,
            "disposition": "current",
        }
        snapshot.setdefault("plate", {}).setdefault(lane, []).append(current)
        candidate["disposition"] = "current"
        cake["current_slice_links"] = [
            *(cake.get("current_slice_links") or []),
            candidate_ref,
        ]
        cake["next_slice"] = None
        return

    if action == "exit":
        current = _find(plate, operation["plate_slice"], "Slice on Plate")
        disposition = normalize(operation.get("disposition", ""))
        if disposition not in {"finished", "paused", "abandoned"}:
            raise CakeError("A Plate exit must be Finished, Paused, or Abandoned")
        reason = operation.get("reason")
        if disposition == "abandoned" and not (reason and str(reason).strip()):
            raise CakeError("An Abandoned Slice needs a reason")
        for lane in ("eating", "blocked"):
            collection = snapshot.get("plate", {}).get(lane, [])
            if current in collection:
                collection.remove(current)
                break
        slice_ref = current.get("slice") or current.get("url") or current.get("id")
        matching = [candidate for candidate in _slice_records(snapshot) if _record_matches(candidate, slice_ref)]
        if matching:
            matching[0]["disposition"] = disposition
            matching[0]["reason"] = reason
        parent = _find(cakes, current["cake"], "parent Cake")
        remaining = [item for item in _plate_records(snapshot) if _record_matches(parent, item.get("cake", ""))]
        parent["current_slice_links"] = [
            trello_card_url(item.get("slice") or item.get("url") or item.get("id"))
            for item in remaining
        ]
        if remaining:
            if operation.get("next_slice") or operation.get("cake_state"):
                raise CakeError("Do not resolve the parent while another of its Slices remains on Plate")
            return
        if operation.get("next_slice"):
            if parent.get("state") != "on_stand":
                raise CakeError("Only a Cake on the Cake Stand can receive a Next Slice")
            candidate = _candidate_for(snapshot, parent, operation["next_slice"])
            parent["next_slice"] = trello_card_url(candidate.get("url") or candidate.get("id"))
            return
        target = operation.get("cake_state")
        if target not in {"parked", "finished"}:
            raise CakeError(
                "When a Cake's last Plate Slice exits, nominate another Slice or Park/Finish the Cake"
            )
        _move_cake(snapshot, parent, target)
        parent["current_slice_links"] = []
        parent["next_slice"] = None
        return

    if action == "move_cake":
        cake = _find(cakes, operation["cake"], "Cake")
        source = cake.get("state")
        target = normalize(operation.get("to", "")).replace(" ", "_")
        allowed = {
            "pantry": {"on_stand"},
            "on_stand": {"parked", "finished"},
            "parked": {"on_stand", "finished"},
            "finished": {"on_stand"},
        }
        if target not in allowed.get(source, set()):
            raise CakeError(f"A Cake cannot move from {source!r} to {target!r}")
        current = [item for item in plate if _record_matches(cake, item.get("cake", ""))]
        if source == "on_stand" and target != "on_stand" and current:
            raise CakeError("Resolve every current Slice before moving its Cake off the Cake Stand")
        for field in ("direction", "finished_when"):
            if field in operation:
                cake[field] = operation[field] or None
        if "next_slice" in operation:
            candidate = _candidate_for(snapshot, cake, operation["next_slice"])
            cake["next_slice"] = trello_card_url(candidate.get("url") or candidate.get("id"))
        if target == "on_stand":
            if not cake.get("direction"):
                raise CakeError("A Cake needs a Direction before promotion")
            if not current and not cake.get("next_slice"):
                raise CakeError("A Cake needs a valid Next Slice before promotion")
            if cake.get("next_slice"):
                _candidate_for(snapshot, cake, cake["next_slice"])
        _move_cake(snapshot, cake, target)
        if target in {"parked", "finished"}:
            cake["current_slice_links"] = []
            cake["next_slice"] = None
        return

    if action == "archive_cake":
        parked = snapshot.get("cake_stand", {}).get("parked", [])
        cake = _find(parked, operation["cake"], "Parked Cake")
        if any(_record_matches(cake, item.get("cake", "")) for item in plate):
            raise CakeError("A Cake with a current Slice cannot be archived")
        parked.remove(cake)
        cake["former_state"] = "parked"
        cake["state"] = "archived"
        snapshot.setdefault("archived_cakes", []).append(cake)
        return

    if action == "reorder":
        collection_name = operation.get("collection")
        collections = {
            "on_stand": snapshot.get("cake_stand", {}).get("on_stand", []),
            "eating": snapshot.get("plate", {}).get("eating", []),
            "blocked": snapshot.get("plate", {}).get("blocked", []),
        }
        if collection_name not in collections:
            raise CakeError("Only Cake Stand and Plate order carry priority meaning")
        collection = collections[collection_name]
        record = _find(collection, operation["record"], "record to reorder")
        position = operation.get("position")
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position < 0
            or position >= len(collection)
        ):
            raise CakeError("Reorder position must be a valid zero-based index")
        collection.remove(record)
        collection.insert(position, record)
        return

    raise CakeError(f"Unknown transition action {action!r}")


def _capacity_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    return {
        "cake_stand": len(snapshot.get("cake_stand", {}).get("on_stand", [])),
        "plate": len(_plate_records(snapshot)),
        "plate:eating": len(snapshot.get("plate", {}).get("eating", [])),
        "plate:blocked": len(snapshot.get("plate", {}).get("blocked", [])),
    }


def _capacity_assessment(
    source: dict[str, Any], target: dict[str, Any], policies: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    before = _capacity_counts(source)
    after = _capacity_counts(target)
    result: list[dict[str, Any]] = []
    for policy in policies:
        if not isinstance(policy, dict):
            raise CakeError("Every capacity policy must be a JSON object")
        scope = policy.get("scope")
        limit = policy.get("limit")
        if (
            scope not in after
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 0
        ):
            raise CakeError("Capacity policies need a known scope and non-negative integer limit")
        if after[scope] > limit:
            result.append(
                {
                    "scope": scope,
                    "label": policy.get("label") or scope,
                    "limit": limit,
                    "before": before[scope],
                    "after": after[scope],
                    "over_by": after[scope] - limit,
                    "severity": "strong_warning",
                    "blocking": False,
                }
            )
    return result


def _issue_key(issue: dict[str, Any]) -> str:
    return json.dumps(issue, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _operation_references(
    snapshot: dict[str, Any], operations: list[dict[str, Any]]
) -> set[str]:
    references: set[str] = set()
    for operation in operations:
        for field in ("cake", "slice", "plate_slice", "record", "next_slice"):
            reference = canonical_ref(operation.get(field))
            if reference:
                references.add(reference)
    records = [*_cake_records(snapshot), *_plate_records(snapshot), *_slice_records(snapshot)]
    for record in records:
        record_references = {
            canonical_ref(record.get(field))
            for field in ("id", "url", "slice", "cake", "next_slice")
            if record.get(field)
        }
        if record_references & references:
            references.update(reference for reference in record_references if reference)
    return references


def _issue_touches(issue: dict[str, Any], references: set[str]) -> bool:
    return any(
        canonical_ref(issue.get(field)) in references
        for field in ("cake", "slice", "source")
        if isinstance(issue.get(field), str)
    )


def _relevant_source_failures(
    snapshot: dict[str, Any], operations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    references = _operation_references(snapshot, operations)
    source_dependent_cakes: set[str] = set()
    for operation in operations:
        if operation.get("action") in {"nominate", "pull", "archive_cake"} or (
            operation.get("action") == "move_cake"
            and normalize(operation.get("to", "")).replace(" ", "_") == "on_stand"
        ):
            reference = canonical_ref(operation.get("cake"))
            if reference:
                source_dependent_cakes.add(reference)
        if operation.get("action") == "exit" and operation.get("next_slice"):
            plate_reference = operation.get("plate_slice")
            for current in _plate_records(snapshot):
                if plate_reference and _record_matches(current, plate_reference):
                    reference = canonical_ref(current.get("cake"))
                    if reference:
                        source_dependent_cakes.add(reference)
    for cake in _cake_records(snapshot):
        aliases = {
            canonical_ref(cake.get("id")),
            canonical_ref(cake.get("url")),
        }
        if aliases & source_dependent_cakes:
            source_dependent_cakes.update(alias for alias in aliases if alias)
    failures: list[dict[str, Any]] = []
    for health in snapshot.get("source_health", []):
        if health.get("status") not in {"unavailable", "unsupported", "drift"}:
            continue
        relevance = health.get("relevance")
        if relevance == "plate_membership" and any(
            operation.get("action") in {"nominate", "pull", "exit", "archive_cake"}
            or (
                operation.get("action") == "reorder"
                and operation.get("collection") in {"eating", "blocked"}
            )
            for operation in operations
        ):
            failures.append(health)
            continue
        if relevance == "cake_stand_membership" and any(
            operation.get("action") in {"nominate", "pull", "move_cake", "archive_cake"}
            or (
                operation.get("action") == "reorder"
                and operation.get("collection") == "on_stand"
            )
            for operation in operations
        ):
            failures.append(health)
            continue
        if relevance in {"current_slice", "next_slice"}:
            source = canonical_ref(health.get("source"))
            if source in references:
                failures.append(health)
            continue
        cake = canonical_ref(health.get("cake"))
        if cake and cake in source_dependent_cakes:
            failures.append(health)
    return failures


def _token_record(record: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: record.get(field) for field in fields}


def _transition_source_projection(
    snapshot: dict[str, Any],
    operations: list[dict[str, Any]],
    policies: list[dict[str, Any]],
) -> dict[str, Any]:
    """Select state whose change can alter this transition or its concrete writes."""

    cakes = _cake_records(snapshot)
    plate = _plate_records(snapshot)
    slices = _slice_records(snapshot)
    selected_cakes: dict[str, dict[str, Any]] = {}
    selected_plate: dict[str, dict[str, Any]] = {}
    selected_slices: dict[str, dict[str, Any]] = {}
    reordered_collections: dict[str, list[dict[str, Any]]] = {}
    include_plate_membership = False
    include_capacity = bool(policies)

    def key_for(record: dict[str, Any]) -> str:
        return canonical_ref(record.get("url") or record.get("id")) or str(id(record))

    def add_cake(reference: str | None) -> dict[str, Any] | None:
        if not reference:
            return None
        matches = [record for record in cakes if _record_matches(record, reference)]
        if len(matches) != 1:
            return None
        record = matches[0]
        selected_cakes[key_for(record)] = record
        return record

    def add_slice(reference: str | None) -> dict[str, Any] | None:
        if not reference:
            return None
        matches = [record for record in slices if _record_matches(record, reference)]
        if len(matches) != 1:
            return None
        record = matches[0]
        selected_slices[key_for(record)] = record
        add_cake(record.get("cake"))
        return record

    def add_plate(reference: str | None) -> dict[str, Any] | None:
        if not reference:
            return None
        matches = [record for record in plate if _record_matches(record, reference)]
        if len(matches) != 1:
            return None
        record = matches[0]
        selected_plate[key_for(record)] = record
        add_cake(record.get("cake"))
        add_slice(record.get("slice") or record.get("url"))
        return record

    def add_plate_for_cake(cake_record: dict[str, Any] | None) -> None:
        if not cake_record:
            return
        for record in plate:
            if record.get("cake") and _record_matches(cake_record, record["cake"]):
                add_plate(record.get("url") or record.get("id"))

    for operation in operations:
        action = operation.get("action")
        if action == "nominate":
            add_cake(operation.get("cake"))
            add_slice(operation.get("slice"))
            include_plate_membership = True
        elif action == "pull":
            cake_record = add_cake(operation.get("cake"))
            add_slice(cake_record.get("next_slice") if cake_record else None)
            include_plate_membership = True
            include_capacity = True
        elif action == "exit":
            plate_record = add_plate(operation.get("plate_slice"))
            cake_record = add_cake(plate_record.get("cake") if plate_record else None)
            add_plate_for_cake(cake_record)
            add_slice(operation.get("next_slice"))
            include_capacity = True
        elif action == "move_cake":
            cake_record = add_cake(operation.get("cake"))
            add_plate_for_cake(cake_record)
            add_slice(operation.get("next_slice"))
            include_capacity = True
        elif action == "archive_cake":
            cake_record = add_cake(operation.get("cake"))
            add_plate_for_cake(cake_record)
            include_plate_membership = True
        elif action == "reorder":
            collection_name = operation.get("collection")
            collection = {
                "on_stand": snapshot.get("cake_stand", {}).get("on_stand", []),
                "eating": snapshot.get("plate", {}).get("eating", []),
                "blocked": snapshot.get("plate", {}).get("blocked", []),
            }.get(collection_name, [])
            reordered_collections[str(collection_name)] = [
                _token_record(record, ("id", "url", "slice", "cake", "position"))
                for record in collection
            ]
            if collection_name == "on_stand":
                add_cake(operation.get("record"))
            else:
                add_plate(operation.get("record"))

    plate_membership = []
    if include_plate_membership:
        plate_membership = [
            _token_record(record, ("id", "url", "slice", "cake", "lane"))
            for record in plate
        ]

    relevant_references = _operation_references(snapshot, operations)
    relevant_health = [
        health
        for health in snapshot.get("source_health", [])
        if any(
            canonical_ref(health.get(field)) in relevant_references
            for field in ("cake", "source")
            if isinstance(health.get(field), str)
        )
    ]
    return {
        "priority": snapshot.get("priority"),
        "sources": snapshot.get("sources"),
        "cakes": [
            _token_record(
                record,
                (
                    "id",
                    "url",
                    "name",
                    "state",
                    "direction",
                    "finished_when",
                    "current_slice_links",
                    "next_slice",
                    "position",
                ),
            )
            for _, record in sorted(selected_cakes.items())
        ],
        "plate": [
            _token_record(
                record,
                (
                    "id",
                    "url",
                    "name",
                    "plate_card",
                    "cake",
                    "slice",
                    "lane",
                    "canonical_state",
                    "outcome",
                    "success",
                    "not_included",
                    "github_issue",
                ),
            )
            for _, record in sorted(selected_plate.items())
        ],
        "slices": [
            _token_record(
                record,
                (
                    "id",
                    "url",
                    "name",
                    "cake",
                    "outcome",
                    "success",
                    "not_included",
                    "github_issue",
                    "disposition",
                    "canonical_state",
                    "adapter",
                ),
            )
            for _, record in sorted(selected_slices.items())
        ],
        "plate_membership": plate_membership,
        "collections": reordered_collections,
        "capacity": _capacity_counts(snapshot) if include_capacity else None,
        "source_health": relevant_health,
    }


def preview_transition(
    snapshot: dict[str, Any],
    operations: list[dict[str, Any]],
    capacity_policies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Preview one coherent transition plan against an immutable source snapshot."""

    if not operations:
        raise CakeError("A transition plan needs at least one operation")
    target = deepcopy(snapshot)
    for index, operation in enumerate(operations):
        _apply_operation(target, operation, index)
    source_validation = validate_snapshot(snapshot)
    validation = validate_snapshot(target)
    source_error_keys = {_issue_key(issue) for issue in source_validation["errors"]}
    references = _operation_references(snapshot, operations)
    blocking_issues = [
        issue
        for issue in validation["errors"]
        if _issue_key(issue) not in source_error_keys or _issue_touches(issue, references)
    ]
    source_failures = _relevant_source_failures(snapshot, operations)
    if source_failures:
        raise CakeError(
            "A source required by this transition is unavailable: "
            + json.dumps(source_failures, ensure_ascii=False, sort_keys=True)
        )
    if blocking_issues:
        raise CakeError(
            "The transition would violate Cake invariants: "
            + json.dumps(blocking_issues, ensure_ascii=False, sort_keys=True)
        )
    policies = capacity_policies or []
    capacity_warnings = _capacity_assessment(snapshot, target, policies)
    token_payload = {
        "source": _transition_source_projection(snapshot, operations, policies),
        "operations": operations,
        "capacity_policies": policies,
    }
    return {
        "status": "preview",
        "confirmation_token": token_for(token_payload),
        "operations": operations,
        "capacity_warnings": capacity_warnings,
        "source_issues": source_validation,
        "target_issues": validation,
        "target": target,
    }
