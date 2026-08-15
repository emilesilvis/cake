"""Provider-independent Cake contracts, invariants, and transition previews."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Iterable


CAKE_FIELDS = (
    "Direction",
    "Finished when",
    "Repository",
    # Read the old field while existing Cake cards migrate to the human-facing
    # Available slices projection. New Cake contracts do not write it.
    "Slice index",
    "Current slices",
    "Next slice",
    "Available slices",
)
SLICE_FIELDS = (
    "Cake",
    "Outcome",
    "Success",
    "Not included",
    "Plate",
    # Read the old field so a migration can identify it. New Slice records do
    # not write delivery links: a GitHub issue is itself canonical when the
    # parent Cake declares a repository.
    "GitHub issue",
    "Disposition",
    "Reason",
)
PLATE_PROJECTION_FIELDS = ("Slice", "Cake", "Disposition")
TERMINAL_SLICE_DISPOSITIONS = {"finished", "abandoned"}
TERMINAL_CANONICAL_STATES = {"finished", "abandoned", "closed"}
SLICE_DISPOSITIONS = {"candidate", "current", "paused", *TERMINAL_SLICE_DISPOSITIONS}
CAKE_STATES = {"pantry", "on_stand", "parked", "finished"}

_CONTRACT_FIELD_LINE = re.compile(
    r"^(?:\*\*(?P<markdown>[^:\n*]+):\*\*|(?P<plain>[^:\n]+):)\s*(?P<value>.*)$"
)


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


def github_repository_name(value: str | None) -> str | None:
    """Return ``owner/repository`` from a supported GitHub repository reference."""

    if not value:
        return None
    match = re.fullmatch(
        r"(?:https://github\.com/)?([^/\s]+/[^/\s#?]+?)(?:\.git)?/?",
        value.strip(),
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def github_repository_url(value: str) -> str:
    repository = github_repository_name(value)
    if not repository:
        raise CakeError("A Cake Repository must be a GitHub repository URL or owner/repository")
    return f"https://github.com/{repository}"


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


def parse_contract_field_line(line: str) -> tuple[str, str] | None:
    """Read a plain or Trello Markdown contract field line."""

    match = _CONTRACT_FIELD_LINE.match(line)
    if not match:
        return None
    return (match.group("markdown") or match.group("plain"), match.group("value"))


def _parse_fields(text: str, allowed: Iterable[str]) -> dict[str, str]:
    allowed_by_normalized = {normalize(field): field for field in allowed}
    result: dict[str, str] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        parsed = parse_contract_field_line(raw_line)
        normalized = normalize(parsed[0]) if parsed else ""
        if parsed and normalized in allowed_by_normalized:
            current = allowed_by_normalized[normalized]
            result[current] = parsed[1].strip()
            continue
        if parsed:
            if current and raw_line.lstrip().startswith("- "):
                result[current] = f"{result[current]}\n{raw_line.rstrip()}".strip()
                continue
            current = None
            continue
        if current and raw_line.strip():
            result[current] = f"{result[current]}\n{raw_line.rstrip()}".strip()
    return result


def _format_fields(
    values: Iterable[tuple[str, str | None]], *, trello_markdown: bool = False
) -> str:
    fields = [
        f"{'**' if trello_markdown else ''}{field}:{'**' if trello_markdown else ''} "
        f"{value.strip()}"
        for field, value in values
        if value and value.strip()
    ]
    return ("\n\n" if trello_markdown else "\n").join(fields)


def _parse_reference_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [
        line.strip().removeprefix("- ").strip()
        for line in value.splitlines()
        if line.strip().removeprefix("- ").strip()
    ]


def _canonical_slice_url(value: str) -> str:
    if is_trello_card_url(value):
        return trello_card_url(value)
    if is_github_issue_url(value):
        return value.strip().rstrip("/")
    raise CakeError("A Slice reference must be a Trello card URL or GitHub issue URL")


def _format_reference_list(values: Iterable[str], *, plate_only: bool = False) -> str | None:
    canonical: list[str] = []
    seen: set[str] = set()
    for value in values:
        reference = trello_card_url(value) if plate_only else _canonical_slice_url(value)
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
        "repository": fields.get("Repository") or None,
        "slice_index": _parse_reference_list(fields.get("Slice index")),
        "current_slice_links": _parse_reference_list(fields.get("Current slices")),
        "next_slice": fields.get("Next slice") or None,
        "available_slices": _parse_reference_list(fields.get("Available slices")),
    }


def format_cake_contract(
    direction: str,
    next_slice: str | None = None,
    finished_when: str | None = None,
    current_slices: Iterable[str] | None = None,
    repository: str | None = None,
    available_slices: Iterable[str] | None = None,
    *,
    trello_markdown: bool = False,
) -> str:
    if not direction.strip():
        raise CakeError("A mature Cake needs a Direction")
    current_slice_links = _format_reference_list(current_slices or [], plate_only=True)
    canonical_available = _format_reference_list(available_slices or [])
    canonical_repository = github_repository_url(repository) if repository else None
    canonical_next = _canonical_slice_url(next_slice) if next_slice else None
    if current_slice_links and canonical_next:
        raise CakeError("A Cake cannot have Current slices and a Next slice at the same time")
    return _format_fields(
        (
            ("Direction", direction),
            ("Finished when", finished_when),
            ("Repository", canonical_repository),
            ("Current slices", current_slice_links),
            ("Next slice", canonical_next),
            ("Available slices", canonical_available),
        ),
        trello_markdown=trello_markdown,
    )


def parse_slice_contract(text: str) -> dict[str, str | None]:
    fields = _parse_fields(text, SLICE_FIELDS)
    disposition = normalize(fields.get("Disposition", "candidate")) or "candidate"
    return {
        "cake": fields.get("Cake") or None,
        "outcome": fields.get("Outcome") or None,
        "success": fields.get("Success") or None,
        "not_included": fields.get("Not included") or None,
        "plate": fields.get("Plate") or None,
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
    plate: str | None = None,
    github_issue: str | None = None,
    *,
    trello_markdown: bool = False,
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
    if plate and not is_trello_card_url(plate):
        raise CakeError("A Slice's Plate projection must be a Trello card URL")
    return _format_fields(
        (
            ("Cake", canonical_cake),
            ("Outcome", outcome),
            ("Success", success),
            ("Not included", not_included),
            ("Plate", trello_card_url(plate) if plate else None),
            ("GitHub issue", github_issue),
            ("Disposition", normalized_disposition.title()),
            ("Reason", reason),
        ),
        trello_markdown=trello_markdown,
    )


def parse_plate_projection_contract(text: str) -> dict[str, str | None]:
    fields = _parse_fields(text, PLATE_PROJECTION_FIELDS)
    return {
        "slice": fields.get("Slice") or None,
        "cake": fields.get("Cake") or None,
        "disposition": normalize(fields.get("Disposition", "current")) or "current",
    }


def format_plate_projection_contract(
    slice_reference: str,
    cake: str,
    *,
    disposition: str = "current",
    trello_markdown: bool = False,
) -> str:
    if not is_github_issue_url(slice_reference):
        raise CakeError("A Plate projection must point to a GitHub issue Slice")
    normalized_disposition = normalize(disposition)
    if normalized_disposition not in {"current", "migrated"}:
        raise CakeError("A Plate projection disposition must be Current or Migrated")
    return _format_fields(
        (
            ("Slice", _canonical_slice_url(slice_reference)),
            ("Cake", trello_card_url(cake)),
            ("Disposition", normalized_disposition.title()),
        ),
        trello_markdown=trello_markdown,
    )


def _record_matches(record: dict[str, Any], reference: str) -> bool:
    expected = canonical_ref(reference)
    candidates = (
        record.get("id"),
        record.get("url"),
        record.get("slice"),
        record.get("plate_card"),
    )
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


def _slice_record_url(record: dict[str, Any]) -> str:
    value = record.get("url") or record.get("id")
    if not isinstance(value, str) or not value.strip():
        raise CakeError("A canonical Slice record needs a stable URL")
    return _canonical_slice_url(value)


def _plate_reference(record: dict[str, Any]) -> str | None:
    value = record.get("plate_card")
    if isinstance(value, str) and value.strip():
        return trello_card_url(value) if is_trello_card_url(value) else value
    if record.get("adapter") == "plate":
        value = record.get("url") or record.get("id")
        if isinstance(value, str) and is_trello_card_url(value):
            return trello_card_url(value)
    value = record.get("id")
    if isinstance(value, str) and value.startswith("planned:plate-projection:"):
        return value
    return None


def _slice_provider(cake: dict[str, Any]) -> str:
    return "github" if github_repository_name(cake.get("repository")) else "plate"


def available_slice_references(
    cake: dict[str, Any],
    catalog: Iterable[dict[str, Any]],
    *,
    current_references: Iterable[str] = (),
    next_slice: str | None | object = ...,
) -> list[str]:
    """Return every viable inactive Slice except the Cake's nominated Next Slice."""

    if cake.get("state") in {"finished", "archived"}:
        return []
    effective_next = cake.get("next_slice") if next_slice is ... else next_slice
    excluded = {
        key
        for key in (
            canonical_ref(effective_next if isinstance(effective_next, str) else None),
            *(canonical_ref(reference) for reference in current_references),
        )
        if key
    }
    eligible: dict[str, tuple[str, dict[str, Any]]] = {}
    for record in catalog:
        if (
            record.get("adapter") != _slice_provider(cake)
            or not record.get("cake")
            or not _record_matches(cake, record["cake"])
            or not record.get("outcome")
            or not record.get("success")
            or normalize(record.get("disposition", "candidate")) not in {"candidate", "paused"}
        ):
            continue
        try:
            reference = _slice_record_url(record)
        except CakeError:
            continue
        key = canonical_ref(reference)
        if key and key not in excluded:
            eligible[key] = (reference, record)

    result: list[str] = []
    seen: set[str] = set()
    for reference in cake.get("available_slices") or []:
        key = canonical_ref(reference)
        if key in eligible and key not in seen:
            result.append(eligible[key][0])
            seen.add(key)
    missing = sorted(
        (value for key, value in eligible.items() if key not in seen),
        key=lambda value: (normalize(value[1].get("name", "")), normalize(value[0])),
    )
    result.extend(reference for reference, _ in missing)
    return result


def _without_reference(values: Iterable[str], reference: str | None) -> list[str]:
    key = canonical_ref(reference)
    return [value for value in values if canonical_ref(value) != key]


def _with_reference(values: Iterable[str], reference: str) -> list[str]:
    return [*_without_reference(values, reference), reference]


def validate_snapshot(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return structural errors and external-drift warnings without mutating state."""

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    cakes = _cake_records(snapshot)
    on_stand = snapshot.get("cake_stand", {}).get("on_stand", [])
    plate = _plate_records(snapshot)
    catalog = _slice_records(snapshot)

    current_by_cake: dict[str, list[dict[str, Any]]] = {}
    current_by_slice: dict[str, list[dict[str, Any]]] = {}
    current_keys: set[str] = set()
    for current in plate:
        plate_reference = _plate_reference(current)
        if not plate_reference or (
            not is_trello_card_url(plate_reference)
            and not plate_reference.startswith("planned:plate-projection:")
        ):
            errors.append(
                {
                    "code": "invalid_plate_projection",
                    "slice": current.get("slice") or current.get("url") or current.get("id"),
                }
            )
        cake_ref = current.get("cake")
        if not cake_ref:
            errors.append(
                {
                    "code": "orphan_slice",
                    "slice": current.get("slice") or current.get("url") or current.get("id"),
                }
            )
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
        if key:
            current_by_slice.setdefault(key, []).append(current)

        canonical_matches = [item for item in catalog if key and _record_matches(item, key)]
        if len(canonical_matches) != 1:
            errors.append(
                {
                    "code": "projection_missing_canonical_slice",
                    "slice": current.get("slice") or current.get("url") or current.get("id"),
                }
            )
        elif canonical_matches[0].get("adapter") == "github":
            backlink = canonical_matches[0].get("plate")
            if canonical_ref(backlink) != canonical_ref(plate_reference):
                errors.append(
                    {
                        "code": "plate_projection_link_drift",
                        "slice": canonical_matches[0].get("url") or canonical_matches[0].get("id"),
                        "actual": backlink,
                        "expected": plate_reference,
                    }
                )
        elif canonical_ref(canonical_matches[0].get("url")) != canonical_ref(plate_reference):
            errors.append(
                {
                    "code": "trello_slice_projection_drift",
                    "slice": canonical_matches[0].get("url") or canonical_matches[0].get("id"),
                    "plate": plate_reference,
                }
            )

        if current.get("canonical_state") in TERMINAL_CANONICAL_STATES:
            warnings.append(
                {
                    "code": "terminal_slice_on_plate",
                    "slice": current.get("slice") or current.get("url"),
                    "canonical_state": current.get("canonical_state"),
                }
            )

    for cake in cakes:
        cake_reference = cake.get("url") or cake.get("id")
        repository = cake.get("repository")
        if repository and not github_repository_name(repository):
            errors.append(
                {"code": "invalid_cake_repository", "cake": cake_reference, "repository": repository}
            )

        stored_available = list(cake.get("available_slices") or [])
        invalid_available_links = [
            reference
            for reference in stored_available
            if not (is_trello_card_url(reference) or is_github_issue_url(reference))
        ]
        if invalid_available_links:
            errors.append(
                {
                    "code": "invalid_available_slice_links",
                    "cake": cake_reference,
                    "slices": invalid_available_links,
                }
            )
        expected_available = available_slice_references(
            cake,
            catalog,
            current_references=current_keys,
        )
        actual_keys = [canonical_ref(value) for value in stored_available]
        expected_keys = [canonical_ref(value) for value in expected_available]
        if len(actual_keys) != len(set(actual_keys)) or set(actual_keys) != set(expected_keys):
            warnings.append(
                {
                    "code": "available_slices_drift",
                    "cake": cake_reference,
                    "actual": stored_available,
                    "expected": expected_available,
                }
            )

    for cake in on_stand:
        cake_key = canonical_ref(cake.get("url") or cake.get("id"))
        current = current_by_cake.get(cake_key or "", [])
        next_slice = cake.get("next_slice")
        stored_current = list(cake.get("current_slice_links") or [])
        expected_current: list[str] = []
        for current_slice in current:
            plate_reference = _plate_reference(current_slice)
            if not plate_reference:
                errors.append(
                    {
                        "code": "invalid_current_slice_url",
                        "cake": cake.get("url") or cake.get("id"),
                        "slice": current_slice.get("slice") or current_slice.get("url"),
                    }
                )
            else:
                expected_current.append(plate_reference)
        invalid_current_links = [
            reference for reference in stored_current if not is_trello_card_url(reference)
            and not reference.startswith("planned:plate-projection:")
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
            if not (is_trello_card_url(next_slice) or is_github_issue_url(next_slice)):
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
                    candidate.get("adapter") == _slice_provider(cake)
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
        else:
            parent = parent_matches[0]
            expected_provider = _slice_provider(parent)
            actual_provider = slice_record.get("adapter")
            if actual_provider != expected_provider:
                finding = {
                    "code": "slice_registry_mismatch",
                    "slice": slice_record.get("url") or slice_record.get("id"),
                    "cake": parent.get("url") or parent.get("id"),
                    "actual": actual_provider,
                    "expected": expected_provider,
                }
                if normalize(slice_record.get("disposition", "candidate")) in TERMINAL_SLICE_DISPOSITIONS:
                    warnings.append(finding)
                else:
                    errors.append(finding)

        adapter = slice_record.get("adapter")
        reference = slice_record.get("url") or slice_record.get("id")
        if adapter == "github" and not is_github_issue_url(reference):
            errors.append({"code": "invalid_github_slice_url", "slice": reference})
        if adapter == "plate" and not is_trello_card_url(reference):
            errors.append({"code": "invalid_trello_slice_url", "slice": reference})
        projection = slice_record.get("plate")
        if projection and not (
            is_trello_card_url(projection)
            or str(projection).startswith("planned:plate-projection:")
        ):
            errors.append(
                {"code": "invalid_plate_projection_link", "slice": reference, "plate": projection}
            )
        key = canonical_ref(reference)
        is_current = bool(key and current_by_slice.get(key))
        if adapter == "github" and projection and not is_current:
            errors.append(
                {"code": "stale_plate_projection_link", "slice": reference, "plate": projection}
            )
        if slice_record.get("github_issue"):
            warnings.append(
                {
                    "code": "legacy_delivery_link",
                    "slice": reference,
                    "github_issue": slice_record.get("github_issue"),
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
    if candidate.get("adapter") != _slice_provider(cake):
        raise CakeError("The nominated Slice is not stored with this Cake's Slices")
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
        candidate_url = _slice_record_url(candidate)
        candidate_reference = canonical_ref(candidate_url)
        if any(_current_key(current) == candidate_reference for current in plate):
            raise CakeError("A current Slice cannot also be Next Slice")
        available = cake.get("available_slices") or []
        if cake.get("next_slice"):
            available = _with_reference(available, cake["next_slice"])
        cake["available_slices"] = _without_reference(available, candidate_url)
        cake["next_slice"] = candidate_url
        return

    if action == "pull":
        cake = _find(on_stand, operation["cake"], "Cake on the Cake Stand")
        if not cake.get("next_slice"):
            raise CakeError("Only a Cake's nominated Next Slice can be pulled")
        candidate = _candidate_for(snapshot, cake, cake["next_slice"])
        candidate_ref = _slice_record_url(candidate)
        if any(_current_key(current) == canonical_ref(candidate_ref) for current in plate):
            raise CakeError("The nominated Slice is already on Plate")
        lane = normalize(operation.get("lane", "eating")).replace(" ", "_")
        if lane not in {"eating", "blocked"}:
            raise CakeError("A pulled Slice must enter Eating or Blocked")
        plate_reference = (
            trello_card_url(candidate_ref)
            if candidate.get("adapter") == "plate"
            else f"planned:plate-projection:{index}"
        )
        current = {
            **deepcopy(candidate),
            "id": plate_reference,
            "plate_card": plate_reference,
            "cake": trello_card_url(cake.get("url") or cake.get("id")),
            "slice": candidate_ref,
            "lane": lane,
            "disposition": "current",
        }
        if candidate.get("adapter") == "github":
            current["plate"] = plate_reference
            candidate["plate"] = plate_reference
        snapshot.setdefault("plate", {}).setdefault(lane, []).append(current)
        candidate["disposition"] = "current"
        cake["available_slices"] = _without_reference(
            cake.get("available_slices") or [], candidate_ref
        )
        cake["current_slice_links"] = [
            *(cake.get("current_slice_links") or []),
            plate_reference,
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
            if matching[0].get("adapter") == "github":
                matching[0]["plate"] = None
                matching[0]["canonical_state"] = (
                    "closed" if disposition in TERMINAL_SLICE_DISPOSITIONS else "open"
                )
            elif disposition in TERMINAL_SLICE_DISPOSITIONS:
                matching[0]["canonical_state"] = "archived"
        parent = _find(cakes, current["cake"], "parent Cake")
        if disposition == "paused":
            parent["available_slices"] = _with_reference(
                parent.get("available_slices") or [], str(slice_ref)
            )
        else:
            parent["available_slices"] = _without_reference(
                parent.get("available_slices") or [], str(slice_ref)
            )
        remaining = [item for item in _plate_records(snapshot) if _record_matches(parent, item.get("cake", ""))]
        parent["current_slice_links"] = [
            _plate_reference(item)
            for item in remaining
            if _plate_reference(item)
        ]
        if remaining:
            if operation.get("next_slice") or operation.get("cake_state"):
                raise CakeError("Do not resolve the parent while another of its Slices remains on Plate")
            return
        if operation.get("next_slice"):
            if parent.get("state") != "on_stand":
                raise CakeError("Only a Cake on the Cake Stand can receive a Next Slice")
            candidate = _candidate_for(snapshot, parent, operation["next_slice"])
            next_reference = _slice_record_url(candidate)
            parent["available_slices"] = _without_reference(
                parent.get("available_slices") or [], next_reference
            )
            parent["next_slice"] = next_reference
            return
        target = operation.get("cake_state")
        if target not in {"parked", "finished"}:
            raise CakeError(
                "When a Cake's last Plate Slice exits, nominate another Slice or Park/Finish the Cake"
            )
        _move_cake(snapshot, parent, target)
        parent["current_slice_links"] = []
        parent["next_slice"] = None
        if target == "finished":
            parent["available_slices"] = []
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
            if cake.get("next_slice"):
                cake["available_slices"] = _with_reference(
                    cake.get("available_slices") or [], cake["next_slice"]
                )
            candidate = _candidate_for(snapshot, cake, operation["next_slice"])
            next_reference = _slice_record_url(candidate)
            cake["available_slices"] = _without_reference(
                cake.get("available_slices") or [], next_reference
            )
            cake["next_slice"] = next_reference
        if target == "on_stand":
            if not cake.get("direction"):
                raise CakeError("A Cake needs a Direction before promotion")
            if not current and not cake.get("next_slice"):
                raise CakeError("A Cake needs a valid Next Slice before promotion")
            if current and operation.get("next_slice"):
                raise CakeError("A Cake with a current Slice cannot also receive a Next Slice")
            if current:
                cake["current_slice_links"] = [
                    _plate_reference(item)
                    for item in current
                    if _plate_reference(item)
                ]
                cake["next_slice"] = None
            if cake.get("next_slice"):
                _candidate_for(snapshot, cake, cake["next_slice"])
        _move_cake(snapshot, cake, target)
        if target == "on_stand" and source == "finished":
            cake["available_slices"] = available_slice_references(
                cake,
                _slice_records(snapshot),
                current_references=(
                    str(item.get("slice") or item.get("url") or item.get("id"))
                    for item in current
                ),
            )
        if target in {"parked", "finished"}:
            if target == "parked" and cake.get("next_slice"):
                cake["available_slices"] = _with_reference(
                    cake.get("available_slices") or [], cake["next_slice"]
                )
            elif target == "finished":
                cake["available_slices"] = []
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
                    "repository",
                    "slice_index",
                    "current_slice_links",
                    "next_slice",
                    "available_slices",
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
                    "plate",
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
                    "plate",
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
