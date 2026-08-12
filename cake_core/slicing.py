"""Shape and safely write one canonical Plate Slice without changing portfolio membership."""

from __future__ import annotations

import re
from typing import Any

from .domain import (
    CakeError,
    TERMINAL_SLICE_DISPOSITIONS,
    canonical_ref,
    format_slice_contract,
    normalize,
    parse_slice_contract,
    token_for,
)
from .portfolio import CakePortfolio, _card_ref, _compact_card


BACKLINK_FIELD = "Cake Slice"
CREATED_SLICE_URL = "<created Plate Slice URL>"


def _matches(record: dict[str, Any], reference: str | None) -> bool:
    expected = canonical_ref(reference)
    return expected is not None and expected in {
        canonical_ref(record.get("id")),
        canonical_ref(record.get("url")),
    }


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
            "raw",
        )
    }


def _backlink_body(body: str, slice_url: str | None) -> str:
    """Set or remove the reciprocal Trello Slice link without rewriting issue prose."""

    pattern = re.compile(rf"^{re.escape(BACKLINK_FIELD)}:\s*.*$", flags=re.IGNORECASE | re.MULTILINE)
    cleaned = pattern.sub("", body).strip()
    if not slice_url:
        return cleaned
    backlink = f"{BACKLINK_FIELD}: {slice_url}"
    return f"{cleaned}\n\n{backlink}" if cleaned else backlink


class CakeSlicer:
    """Read/preview/apply interface for one canonical Trello Slice definition."""

    def __init__(self, portfolio: CakePortfolio | None = None):
        self.portfolio = portfolio or CakePortfolio()

    def read_cake(self, reference: str) -> dict[str, Any]:
        snapshot = self.portfolio.snapshot(include_candidates=False)
        return self.portfolio._cake_record(snapshot, reference)

    def _plate_context(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        return self.portfolio._trello_role("plate")

    def _plate_slice(self, reference: str) -> dict[str, Any]:
        plate_board, _ = self._plate_context()
        card = self.portfolio.trello.locate_card(reference)
        if card.get("idBoard") != plate_board["id"]:
            raise CakeError("Every canonical Slice must be a card on the configured Plate board")
        contract = parse_slice_contract(card.get("desc", ""))
        return {
            "id": card["id"],
            "url": card.get("url") or card["id"],
            "name": card.get("name", ""),
            "adapter": "plate",
            "canonical_state": "archived" if card.get("closed") else "open",
            **contract,
            "raw": _compact_card(card),
        }

    def _canonical_slice(
        self,
        cake: dict[str, Any],
        reference: str,
    ) -> dict[str, Any]:
        record = self._plate_slice(reference)
        if not record.get("cake") or not _matches(cake, record["cake"]):
            raise CakeError("The Slice does not belong to the selected parent Cake")
        return record

    def read_slice(self, cake_reference: str, slice_reference: str) -> dict[str, Any]:
        cake = self.read_cake(cake_reference)
        return self._canonical_slice(cake, slice_reference)

    @staticmethod
    def _target(
        cake: dict[str, Any],
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None,
        github_issue: str | None,
        disposition: str,
    ) -> dict[str, str]:
        if not title.strip():
            raise CakeError("A Slice needs a title")
        body = format_slice_contract(
            _card_ref(cake),
            outcome,
            success,
            not_included,
            disposition=disposition,
            github_issue=github_issue,
        )
        return {"title": title.strip(), "body": body}

    def _delivery_write(
        self,
        github_issue: str,
        slice_url: str | None,
    ) -> dict[str, Any]:
        issue = self.portfolio.github.issue(github_issue)
        raw = issue.get("raw", {})
        source_body = raw.get("body", "")
        return {
            "action": "set_github_backlink" if slice_url else "remove_github_backlink",
            "issue": issue.get("url") or github_issue,
            "title": raw.get("title") or issue.get("name", ""),
            "source": {
                "state": raw.get("state"),
                "body": source_body,
            },
            "target_body": _backlink_body(source_body, slice_url),
        }

    def _delivery_writes_for_update(
        self,
        current_issue: str | None,
        target_issue: str | None,
        slice_url: str,
    ) -> list[dict[str, Any]]:
        if canonical_ref(current_issue) == canonical_ref(target_issue):
            return [self._delivery_write(target_issue, slice_url)] if target_issue else []
        writes: list[dict[str, Any]] = []
        if current_issue:
            writes.append(self._delivery_write(current_issue, None))
        if target_issue:
            writes.append(self._delivery_write(target_issue, slice_url))
        return writes

    def preview_create(
        self,
        cake_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        github_issue: str | None = None,
    ) -> dict[str, Any]:
        cake = self.read_cake(cake_reference)
        target = self._target(
            cake,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            github_issue=github_issue,
            disposition="candidate",
        )
        plate_board, lists = self._plate_context()
        write = {
            "action": "create_archived_plate_card",
            "board": {"id": plate_board["id"], "name": plate_board.get("name")},
            "list": {"id": lists["eating"]["id"], "name": lists["eating"].get("name")},
            **target,
        }
        delivery_writes = (
            [self._delivery_write(github_issue, CREATED_SLICE_URL)] if github_issue else []
        )
        payload = {
            "operation": "create_slice",
            "parent": _parent_state(cake),
            "write": write,
            "delivery_writes": delivery_writes,
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
        github_issue: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_create(
            cake_reference,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            github_issue=github_issue,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the parent, destination, draft, or delivery link changed")
        write = preview["write"]
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

        created_url = created.get("url") or created["id"]
        created_ref = _card_ref(created)
        for delivery in preview["delivery_writes"]:
            body = _backlink_body(delivery["source"]["body"], created_ref)
            try:
                self.portfolio.github.update_issue(
                    delivery["issue"], title=delivery["title"], body=body
                )
            except CakeError as exc:
                raise CakeError(
                    f"Slice {created_url} was created and archived, but GitHub backlinking failed; "
                    f"reconcile {delivery['issue']} before continuing. Cause: {exc}"
                ) from None

        contract = parse_slice_contract(created.get("desc", write["body"]))
        record = {
            "id": created["id"],
            "url": created_url,
            "name": created.get("name", write["title"]),
            "adapter": "plate",
            "canonical_state": "archived",
            **contract,
        }
        return {"status": "created", "slice": record}

    def preview_update(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        github_issue: str | None = None,
    ) -> dict[str, Any]:
        cake = self.read_cake(cake_reference)
        current = self._canonical_slice(cake, slice_reference)
        disposition = normalize(current.get("disposition", "candidate")) or "candidate"
        if disposition in TERMINAL_SLICE_DISPOSITIONS:
            raise CakeError("A Finished or Abandoned Slice cannot be reshaped")
        if current.get("canonical_state") == "open":
            disposition = "current"
        target = self._target(
            cake,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            github_issue=github_issue,
            disposition=disposition,
        )
        write = {
            "action": "update_plate_card",
            "slice": current.get("url") or current["id"],
            **target,
        }
        delivery_writes = self._delivery_writes_for_update(
            current.get("github_issue"), github_issue, _card_ref(current)
        )
        payload = {
            "operation": "update_slice",
            "parent": _parent_state(cake),
            "source": current,
            "write": write,
            "delivery_writes": delivery_writes,
        }
        return {
            "status": "preview",
            "confirmation_token": token_for(payload),
            **payload,
        }

    def preview_adopt(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        github_issue: str | None = None,
    ) -> dict[str, Any]:
        """Preview assigning a parent to an otherwise parentless Plate card."""

        cake = self.read_cake(cake_reference)
        current = self._plate_slice(slice_reference)
        if current.get("cake"):
            raise CakeError(
                "Adopt only repairs a parentless Slice; it cannot reparent an existing Slice"
            )
        disposition = normalize(current.get("disposition", "candidate")) or "candidate"
        if disposition in TERMINAL_SLICE_DISPOSITIONS:
            raise CakeError("A Finished or Abandoned Slice cannot be adopted")
        if current.get("canonical_state") == "open":
            disposition = "current"
        target = self._target(
            cake,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            github_issue=github_issue,
            disposition=disposition,
        )
        write = {
            "action": "adopt_parentless_plate_card",
            "slice": current.get("url") or current["id"],
            **target,
        }
        delivery_writes = self._delivery_writes_for_update(
            current.get("github_issue"), github_issue, _card_ref(current)
        )
        payload = {
            "operation": "adopt_slice",
            "parent": _parent_state(cake),
            "source": current,
            "write": write,
            "delivery_writes": delivery_writes,
        }
        return {
            "status": "preview",
            "confirmation_token": token_for(payload),
            **payload,
        }

    def adopt(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        github_issue: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_adopt(
            cake_reference,
            slice_reference,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            github_issue=github_issue,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the parent, Slice, draft, or delivery link changed")
        write = preview["write"]
        current = preview["source"]
        card = self.portfolio.trello.update_card(
            current["id"], name=write["title"], description=write["body"]
        )
        for delivery in preview["delivery_writes"]:
            try:
                self.portfolio.github.update_issue(
                    delivery["issue"],
                    title=delivery["title"],
                    body=delivery["target_body"],
                )
            except CakeError as exc:
                raise CakeError(
                    f"Slice {current['url']} was adopted, but GitHub cross-linking failed; "
                    f"reconcile {delivery['issue']} before continuing. Cause: {exc}"
                ) from None
        adopted = {
            "id": card["id"],
            "url": card.get("url") or card["id"],
            "name": card.get("name", write["title"]),
            "adapter": "plate",
            "canonical_state": "archived" if card.get("closed") else "open",
            **parse_slice_contract(card.get("desc", write["body"])),
        }
        return {"status": "adopted", "slice": adopted}

    def update(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        github_issue: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_update(
            cake_reference,
            slice_reference,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            github_issue=github_issue,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the parent, Slice, draft, or delivery link changed")
        write = preview["write"]
        current = preview["source"]
        card = self.portfolio.trello.update_card(
            current["id"], name=write["title"], description=write["body"]
        )
        for delivery in preview["delivery_writes"]:
            try:
                self.portfolio.github.update_issue(
                    delivery["issue"],
                    title=delivery["title"],
                    body=delivery["target_body"],
                )
            except CakeError as exc:
                raise CakeError(
                    f"Slice {current['url']} was updated, but GitHub cross-linking failed; "
                    f"reconcile {delivery['issue']} before continuing. Cause: {exc}"
                ) from None
        updated = {
            "id": card["id"],
            "url": card.get("url") or card["id"],
            "name": card.get("name", write["title"]),
            "adapter": "plate",
            "canonical_state": "archived" if card.get("closed") else "open",
            **parse_slice_contract(card.get("desc", write["body"])),
        }
        return {"status": "updated", "slice": updated}
