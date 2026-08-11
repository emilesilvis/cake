"""Shape and safely write one canonical Slice without changing portfolio membership."""

from __future__ import annotations

import re
import shlex
from typing import Any

from .domain import (
    CakeError,
    TERMINAL_SLICE_DISPOSITIONS,
    canonical_ref,
    format_slice_contract,
    normalize,
    parse_slice_contract,
    parse_slice_source,
    token_for,
)
from .portfolio import CakePortfolio, _compact_card, _reference_field
from .providers import github_issue_parts, is_github_issue


def _matches(record: dict[str, Any], reference: str | None) -> bool:
    expected = canonical_ref(reference)
    return expected is not None and expected in {
        canonical_ref(record.get("id")),
        canonical_ref(record.get("url")),
    }


def _write_query_labels(query: str) -> list[str]:
    labels: list[str] = []
    try:
        terms = shlex.split(query)
    except ValueError:
        terms = query.split()
    for term in terms:
        match = re.match(r"^label:(.+)$", term, flags=re.IGNORECASE)
        if match and match.group(1).strip():
            labels.append(match.group(1).strip())
            continue
        normalized = term.casefold()
        if normalized in {"is:issue", "is:open", "state:open", "type:issue"}:
            continue
        if normalized.startswith(("sort:", "order:")):
            continue
        raise CakeError(
            "cake-slice cannot guarantee writes remain in this GitHub query. "
            "Use open/issue, label, sort, and order qualifiers only, or create a matching issue manually."
        )
    return labels


def _parent_state(cake: dict[str, Any]) -> dict[str, Any]:
    return {
        key: cake.get(key)
        for key in (
            "id",
            "url",
            "name",
            "state",
            "direction",
            "finished_when",
            "slice_source",
            "raw",
        )
    }


class CakeSlicer:
    """Read/preview/apply interface for a single canonical Slice definition."""

    def __init__(self, portfolio: CakePortfolio | None = None):
        self.portfolio = portfolio or CakePortfolio()

    def read_cake(self, reference: str) -> dict[str, Any]:
        snapshot = self.portfolio.snapshot(include_candidates=False)
        return self.portfolio._cake_record(snapshot, reference)

    def _source(
        self, cake: dict[str, Any], supplied_source: str | None
    ) -> tuple[str, dict[str, Any]]:
        stored = cake.get("slice_source")
        if stored and supplied_source:
            if parse_slice_source(stored) != parse_slice_source(supplied_source):
                raise CakeError("The supplied Slice source conflicts with the parent Cake")
        value = stored or supplied_source
        if not value:
            raise CakeError(
                "This Cake has no Slice source yet; supply the source that cake-prioritise will store"
            )
        return value, parse_slice_source(value)

    def _plate_context(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        return self.portfolio._trello_role("plate")

    def _canonical_slice(
        self,
        cake: dict[str, Any],
        source: dict[str, Any],
        reference: str,
    ) -> dict[str, Any]:
        if is_github_issue(reference):
            if source["adapter"] != "github":
                raise CakeError("This Cake's canonical Slices live on Plate, not GitHub")
            repository, _ = github_issue_parts(reference)
            if repository.casefold() != source["repository"].casefold():
                raise CakeError("The GitHub issue is outside the Cake's configured Slice source")
            record = self.portfolio.github.issue(reference)
        else:
            if source["adapter"] != "plate":
                raise CakeError("This Cake's canonical Slices live on GitHub, not Plate")
            plate_board, _ = self._plate_context()
            card = self.portfolio.trello.locate_card(reference)
            if card.get("idBoard") != plate_board["id"]:
                raise CakeError("The Trello card is not on the configured Plate board")
            if _reference_field(card.get("desc", ""), "Slice"):
                raise CakeError("That Plate card is a proxy; pass its canonical Slice link")
            contract = parse_slice_contract(card.get("desc", ""))
            record = {
                "id": card["id"],
                "url": card.get("url") or card["id"],
                "name": card.get("name", ""),
                "adapter": "plate",
                "canonical_state": "archived" if card.get("closed") else "open",
                **contract,
                "raw": _compact_card(card),
            }
        if not record.get("cake") or not _matches(cake, record["cake"]):
            raise CakeError("The Slice does not belong to the selected parent Cake")
        return record

    def read_slice(
        self, cake_reference: str, slice_reference: str, *, slice_source: str | None = None
    ) -> dict[str, Any]:
        cake = self.read_cake(cake_reference)
        _, source = self._source(cake, slice_source)
        return self._canonical_slice(cake, source, slice_reference)

    @staticmethod
    def _target(
        cake: dict[str, Any],
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None,
        disposition: str,
    ) -> dict[str, str]:
        if not title.strip():
            raise CakeError("A Slice needs a title")
        body = format_slice_contract(
            cake["url"], outcome, success, not_included, disposition=disposition
        )
        return {"title": title.strip(), "body": body}

    def preview_create(
        self,
        cake_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        slice_source: str | None = None,
    ) -> dict[str, Any]:
        cake = self.read_cake(cake_reference)
        source_value, source = self._source(cake, slice_source)
        target = self._target(
            cake,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            disposition="candidate",
        )
        if source["adapter"] == "github":
            similar = self.portfolio.github.similar_issues(
                source["repository"], title=target["title"], body=target["body"]
            )
            if similar:
                matches = "; ".join(
                    f"{match['url']} ({match['state']}: {match['title']})"
                    for match in similar[:5]
                )
                raise CakeError(
                    "A GitHub issue may already represent this Slice: "
                    f"{matches}. Review the existing issue and update/adopt it, or reshape "
                    "the Slice so the outcomes are genuinely distinct."
                )
            labels = _write_query_labels(source["query"])
            write = {
                "action": "create_github_issue",
                "repository": source["repository"],
                "query": source["query"],
                "labels": labels,
                **target,
            }
        else:
            plate_board, lists = self._plate_context()
            write = {
                "action": "create_archived_plate_card",
                "board": {"id": plate_board["id"], "name": plate_board.get("name")},
                "list": {"id": lists["eating"]["id"], "name": lists["eating"].get("name")},
                **target,
            }
        payload = {
            "operation": "create_slice",
            "parent": _parent_state(cake),
            "slice_source": source_value,
            "write": write,
        }
        return {
            "status": "preview",
            "confirmation_token": token_for(payload),
            **payload,
        }

    def create(
        self,
        cake_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        slice_source: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_create(
            cake_reference,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            slice_source=slice_source,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the parent, destination, or Slice draft changed")
        write = preview["write"]
        if write["action"] == "create_github_issue":
            created = self.portfolio.github.create_issue(
                write["repository"],
                title=write["title"],
                body=write["body"],
                labels=write["labels"],
            )
        else:
            created = self.portfolio.trello.create_card(
                write["list"]["id"],
                name=write["title"],
                description=write["body"],
            )
            try:
                created = self.portfolio.trello.update_card(created["id"], closed=True)
            except CakeError as first_error:
                try:
                    self.portfolio.trello.update_card(created["id"], closed=True)
                except CakeError:
                    reference = created.get("url") or created.get("id")
                    raise CakeError(
                        f"Slice {reference} was created but could not be archived; archive it before continuing. "
                        f"Cause: {first_error}"
                    ) from None
                created = self.portfolio.trello.card(created["id"])
            contract = parse_slice_contract(created.get("desc", write["body"]))
            created = {
                "id": created["id"],
                "url": created.get("url") or created["id"],
                "name": created.get("name", write["title"]),
                "adapter": "plate",
                "canonical_state": "archived",
                **contract,
            }
        return {"status": "created", "slice": created, "slice_source": preview["slice_source"]}

    def preview_update(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        slice_source: str | None = None,
    ) -> dict[str, Any]:
        cake = self.read_cake(cake_reference)
        source_value, source = self._source(cake, slice_source)
        current = self._canonical_slice(cake, source, slice_reference)
        if source["adapter"] == "github":
            _write_query_labels(source["query"])
        disposition = normalize(current.get("disposition", "candidate")) or "candidate"
        if current.get("adapter") == "github" and current.get("canonical_state") == "closed":
            raise CakeError("A closed GitHub Slice is terminal and cannot be reshaped")
        if disposition in TERMINAL_SLICE_DISPOSITIONS:
            raise CakeError("A Finished or Abandoned Slice cannot be reshaped")
        if current.get("adapter") == "plate" and current.get("canonical_state") == "open":
            disposition = "current"
        target = self._target(
            cake,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            disposition=disposition,
        )
        write = {
            "action": "update_github_issue" if current["adapter"] == "github" else "update_plate_card",
            "slice": current.get("url") or current["id"],
            **target,
        }
        payload = {
            "operation": "update_slice",
            "parent": _parent_state(cake),
            "slice_source": source_value,
            "source": current,
            "write": write,
        }
        return {
            "status": "preview",
            "confirmation_token": token_for(payload),
            **payload,
        }

    def update(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        slice_source: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_update(
            cake_reference,
            slice_reference,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            slice_source=slice_source,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the parent, canonical Slice, or draft changed")
        write = preview["write"]
        current = preview["source"]
        if write["action"] == "update_github_issue":
            updated = self.portfolio.github.update_issue(
                write["slice"], title=write["title"], body=write["body"]
            )
        else:
            card = self.portfolio.trello.update_card(
                current["id"], name=write["title"], description=write["body"]
            )
            updated = {
                "id": card["id"],
                "url": card.get("url") or card["id"],
                "name": card.get("name", write["title"]),
                "adapter": "plate",
                "canonical_state": "archived" if card.get("closed") else "open",
                **parse_slice_contract(card.get("desc", write["body"])),
            }
        return {"status": "updated", "slice": updated}
