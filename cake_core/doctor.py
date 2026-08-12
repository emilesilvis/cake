"""Read-only, human-facing health checks for a Cake portfolio."""

from __future__ import annotations

import re
from typing import Any

from .domain import (
    canonical_ref,
)
from .portfolio import CakePortfolio

_LIMIT_SUFFIX = re.compile(r"(?:^|\s)/\s*(\d+)\s*$")


def _cake_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    stand = snapshot.get("cake_stand", {})
    return [
        *snapshot.get("pantry", []),
        *stand.get("on_stand", []),
        *stand.get("parked", []),
        *stand.get("finished", []),
        *snapshot.get("archived_cakes", []),
    ]


def _slice_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return list(snapshot.get("slice_catalog", []))


def _matches(record: dict[str, Any], reference: str | None) -> bool:
    expected = canonical_ref(reference)
    if not expected:
        return False
    return expected in {
        canonical_ref(record.get("id")),
        canonical_ref(record.get("url")),
        canonical_ref(record.get("slice")),
    }


def _subject(snapshot: dict[str, Any], reference: str | None) -> dict[str, str] | None:
    if not reference:
        return None
    records = [*_cake_records(snapshot), *_slice_records(snapshot)]
    for lane in ("eating", "blocked"):
        records.extend(snapshot.get("plate", {}).get(lane, []))
    match = next((record for record in records if _matches(record, reference)), None)
    if not match:
        return {"name": reference, "url": reference}
    url = match.get("slice") or match.get("url") or reference
    return {"name": match.get("name") or reference, "url": url}


def _display(subject: dict[str, str] | None, fallback: str) -> str:
    return f"“{subject['name']}”" if subject else fallback


def _handoff_for(code: str) -> str | None:
    if code in {
        "invalid_slice_contract",
        "invalid_slice_cake_link",
        "invalid_github_slice_url",
        "invalid_trello_slice_url",
        "invalid_cake_repository",
        "invalid_slice_index_links",
        "slice_index_drift",
        "slice_registry_mismatch",
        "legacy_delivery_link",
    }:
        return "cake-slice"
    if code in {
        "orphan_slice",
        "parent_not_on_stand",
        "duplicate_plate_slice",
        "terminal_slice_on_plate",
        "invalid_current_slice_url",
        "invalid_current_slice_links",
        "current_slice_links_drift",
        "missing_direction",
        "waiting_without_next_slice",
        "invalid_next_slice_link",
        "invalid_next_slice",
        "current_cake_has_queued_slice",
        "next_slice_is_current",
        "invalid_slice_parent",
        "wip_overage",
        "invalid_capacity_contract",
        "invalid_plate_projection",
        "projection_missing_canonical_slice",
        "plate_projection_link_drift",
        "trello_slice_projection_drift",
        "invalid_plate_projection_link",
        "stale_plate_projection_link",
    }:
        return "cake-prioritise"
    return None


def _finding_for_issue(
    snapshot: dict[str, Any], issue: dict[str, Any], severity: str
) -> dict[str, Any]:
    code = str(issue.get("code") or "unknown_issue")
    slice_subject = _subject(snapshot, issue.get("slice"))
    cake_subject = _subject(snapshot, issue.get("cake"))
    slice_name = _display(slice_subject, "A Slice")
    cake_name = _display(cake_subject, "A Cake")
    messages = {
        "orphan_slice": f"{slice_name} is current but has no parent Cake.",
        "parent_not_on_stand": (
            f"{slice_name} is current, but its parent {cake_name} is not on the Cake Stand."
        ),
        "duplicate_plate_slice": f"{slice_name} appears more than once as current work.",
        "terminal_slice_on_plate": f"{slice_name} is current even though it is already closed.",
        "invalid_current_slice_url": f"{cake_name} points to a current Slice with an invalid link.",
        "invalid_current_slice_links": f"{cake_name} contains a non-clickable current Slice link.",
        "current_slice_links_drift": (
            f"{cake_name} does not link to exactly the Slices that are currently on Plate."
        ),
        "missing_direction": f"{cake_name} is on the Stand but has no Direction.",
        "waiting_without_next_slice": (
            f"{cake_name} is waiting on the Stand but does not point to a Next Slice."
        ),
        "invalid_next_slice_link": f"{cake_name} has a non-clickable Next Slice link.",
        "invalid_next_slice": f"{cake_name} points to a Next Slice that is not pull-ready.",
        "current_cake_has_queued_slice": (
            f"{cake_name} has both current work and a Next Slice; those roles are exclusive."
        ),
        "next_slice_is_current": f"{cake_name} names a Slice as Next while it is already current.",
        "invalid_slice_contract": f"{slice_name} is missing part of its Cake, Outcome, or Success contract.",
        "invalid_slice_cake_link": f"{slice_name} does not use a clickable Trello link for its parent Cake.",
        "invalid_slice_parent": f"{slice_name} points to a parent Cake that cannot be resolved.",
        "invalid_github_slice_url": f"{slice_name} is not a valid GitHub issue Slice.",
        "invalid_trello_slice_url": f"{slice_name} is not a valid Trello Slice card.",
        "invalid_cake_repository": f"{cake_name} does not name a valid GitHub repository.",
        "invalid_slice_index_links": f"{cake_name} contains an invalid link in its Slice index.",
        "slice_index_drift": f"{cake_name}'s Slice index does not list exactly its canonical Slices.",
        "slice_registry_mismatch": f"{slice_name} is stored outside {cake_name}'s chosen Slice registry.",
        "legacy_delivery_link": f"{slice_name} still uses the retired Trello-to-GitHub delivery-link model.",
        "invalid_plate_projection": f"{slice_name} has no valid Plate card.",
        "projection_missing_canonical_slice": f"{slice_name}'s Plate card cannot resolve its canonical Slice.",
        "plate_projection_link_drift": f"{slice_name} and its Plate card do not link to each other.",
        "trello_slice_projection_drift": f"{slice_name}'s Plate entry is not its canonical Trello card.",
        "invalid_plate_projection_link": f"{slice_name} has an invalid Plate backlink.",
        "stale_plate_projection_link": f"{slice_name} links to Plate even though it is not current.",
    }
    result: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": messages.get(
            code, f"Cake health check found {code.replace('_', ' ')}."
        ),
        "handoff": _handoff_for(code),
    }
    subjects = [item for item in (slice_subject, cake_subject) if item]
    if subjects:
        result["subjects"] = subjects
    return result


def _contract_fields(description: str) -> set[str]:
    fields: set[str] = set()
    for line in description.splitlines():
        match = re.match(r"^([^:\n]+):", line)
        if match:
            fields.add(" ".join(match.group(1).casefold().strip().split()))
    return fields


def _limit_from_name(name: str | None) -> int | None:
    match = _LIMIT_SUFFIX.search(name or "")
    return int(match.group(1)) if match else None


class CakeDoctor:
    """Inspect current provider state without writing to it."""

    def __init__(self, portfolio: CakePortfolio | None = None):
        self.portfolio = portfolio or CakePortfolio()

    def _wip(
        self, snapshot: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        sources = snapshot.get("sources", {})
        stand_list = sources.get("cake_stand", {}).get("lists", {}).get("on_stand", {})
        eating_list = sources.get("plate", {}).get("lists", {}).get("eating", {})
        blocked_list = sources.get("plate", {}).get("lists", {}).get("blocked", {})
        plate = snapshot.get("plate", {})
        observed = [
            {
                "scope": "cake_stand",
                "label": stand_list.get("name") or "Cake Stand",
                "count": len(snapshot.get("cake_stand", {}).get("on_stand", [])),
                "limit": _limit_from_name(stand_list.get("name")),
            },
            {
                "scope": "plate",
                "label": eating_list.get("name") or "Plate",
                "count": len(plate.get("eating", [])) + len(plate.get("blocked", [])),
                "limit": _limit_from_name(eating_list.get("name")),
            },
        ]
        blocked_limit = _limit_from_name(blocked_list.get("name"))
        if blocked_limit is not None:
            observed.append(
                {
                    "scope": "plate:blocked",
                    "label": blocked_list.get("name") or "Blocked",
                    "count": len(plate.get("blocked", [])),
                    "limit": blocked_limit,
                }
            )
        findings: list[dict[str, Any]] = []
        for item in observed:
            item["status"] = (
                "unobserved"
                if item["limit"] is None
                else "over"
                if item["count"] > item["limit"]
                else "within"
            )
            if item["status"] == "over":
                findings.append(
                    {
                        "severity": "warning",
                        "code": "wip_overage",
                        "message": (
                            f"{item['label']} contains {item['count']} items, "
                            f"above its visible limit of {item['limit']}."
                        ),
                        "handoff": "cake-prioritise",
                    }
                )
        return observed, findings

    def _capacity_findings(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        required = {"cadence", "load", "supports"}
        for card in snapshot.get("capacity_constraints", []):
            fields = _contract_fields(str(card.get("desc") or ""))
            missing = sorted(required - fields)
            if not missing:
                continue
            findings.append(
                {
                    "severity": "error",
                    "code": "invalid_capacity_contract",
                    "message": (
                        f"“{card.get('name') or card.get('url') or card.get('id')}” is missing "
                        + ", ".join(field.title() for field in missing)
                        + "."
                    ),
                    "subjects": [
                        {
                            "name": card.get("name")
                            or card.get("url")
                            or card.get("id"),
                            "url": card.get("url") or card.get("id"),
                        }
                    ],
                    "handoff": "cake-prioritise",
                }
            )
        return findings

    def check(self) -> dict[str, Any]:
        snapshot = self.portfolio.snapshot()
        issues = snapshot.get("issues", {})
        findings = [
            *(
                _finding_for_issue(snapshot, issue, "error")
                for issue in issues.get("errors", [])
            ),
            *(
                _finding_for_issue(snapshot, issue, "warning")
                for issue in issues.get("warnings", [])
            ),
        ]
        for source in snapshot.get("source_health", []):
            severity = (
                "error"
                if source.get("status") in {"unavailable", "unsupported"}
                else "warning"
            )
            findings.append(
                {
                    "severity": severity,
                    "code": f"source_{source.get('status') or 'problem'}",
                    "message": str(
                        source.get("error")
                        or "A configured source could not be verified."
                    ),
                    "subjects": [
                        {
                            "name": str(source.get("source") or "Configured source"),
                            "url": str(source.get("source") or ""),
                        }
                    ],
                    "handoff": None,
                }
            )
        wip, wip_findings = self._wip(snapshot)
        findings.extend(wip_findings)
        findings.extend(self._capacity_findings(snapshot))
        current_slices = [
            *snapshot.get("plate", {}).get("eating", []),
            *snapshot.get("plate", {}).get("blocked", []),
        ]
        prioritisation_needed = any(
            finding.get("handoff") == "cake-prioritise" for finding in findings
        )
        handoffs = sorted(
            {finding["handoff"] for finding in findings if finding.get("handoff")}
        )
        return {
            "status": "healthy" if not findings else "attention",
            "summary": {
                "cakes_on_stand": len(
                    snapshot.get("cake_stand", {}).get("on_stand", [])
                ),
                "current_slices": len(current_slices),
                "capacity_constraints": len(snapshot.get("capacity_constraints", [])),
                "parked_cakes": len(snapshot.get("cake_stand", {}).get("parked", [])),
                "archived_cakes": len(snapshot.get("archived_cakes", [])),
                "findings": len(findings),
            },
            "current_plate": [
                {
                    "name": item.get("name") or item.get("url") or item.get("id"),
                    "url": item.get("slice") or item.get("url") or item.get("id"),
                    "lane": item.get("lane"),
                }
                for item in current_slices
            ],
            "wip": wip,
            "findings": findings,
            "handoffs": handoffs,
            "portfolio_challenge": {
                "required": prioritisation_needed,
                "recommended": bool(current_slices),
                "skill": "cake-prioritise",
                "reason": (
                    "Current membership has a structural or capacity problem."
                    if prioritisation_needed
                    else "Structural health does not by itself endorse the current priorities."
                ),
            },
        }
