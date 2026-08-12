"""Shape and safely write one provider-aware canonical Cake Slice."""

from __future__ import annotations

from typing import Any

from .domain import (
    CakeError,
    TERMINAL_SLICE_DISPOSITIONS,
    canonical_ref,
    format_cake_contract,
    format_plate_projection_contract,
    format_slice_contract,
    github_repository_name,
    github_repository_url,
    normalize,
    parse_slice_contract,
    token_for,
)
from .portfolio import CakePortfolio, _card_ref, _compact_card, _record_matches, _slice_ref


CREATED_GITHUB_SLICE_URL = "<created GitHub Slice URL>"
CREATED_TRELLO_SLICE_URL = "<created Trello Slice URL>"
SLICE_LABEL = "cake-slice"


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
            "repository",
            "slice_index",
            "current_slice_links",
            "current_slices",
            "next_slice",
            "raw",
        )
    }


def _append_reference(values: list[str], reference: str) -> list[str]:
    key = canonical_ref(reference)
    return [
        *[value for value in values if canonical_ref(value) != key],
        reference,
    ]


def _cake_body(
    cake: dict[str, Any],
    *,
    repository: str | None = None,
    slice_index: list[str] | None = None,
    next_slice: str | None | object = ...,
) -> str:
    effective_next = cake.get("next_slice") if next_slice is ... else next_slice
    return format_cake_contract(
        cake.get("direction") or "",
        effective_next if isinstance(effective_next, str) else None,
        cake.get("finished_when"),
        cake.get("current_slices", []),
        repository if repository is not None else cake.get("repository"),
        slice_index if slice_index is not None else list(cake.get("slice_index") or []),
    )


def _preview_cake_body(
    cake: dict[str, Any],
    *,
    provider: str,
    slice_index: list[str],
    repository: str | None = None,
    next_slice: str | None | object = ...,
) -> str:
    if provider == "github":
        dummy = "https://github.com/cake/created-slice/issues/0"
        placeholder = CREATED_GITHUB_SLICE_URL
    else:
        dummy = "https://trello.com/c/createdSlice"
        placeholder = CREATED_TRELLO_SLICE_URL
    body = _cake_body(
        cake,
        repository=repository,
        slice_index=[dummy if value == placeholder else value for value in slice_index],
        next_slice=dummy if next_slice == placeholder else next_slice,
    )
    return body.replace(dummy, placeholder)


class CakeSlicer:
    """Read, preview, and apply canonical Slice definition writes."""

    def __init__(self, portfolio: CakePortfolio | None = None):
        self.portfolio = portfolio or CakePortfolio()

    def _snapshot_and_cake(
        self, reference: str, *, include_candidates: bool = True
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        snapshot = self.portfolio.snapshot(include_candidates=include_candidates)
        return snapshot, self.portfolio._cake_record(snapshot, reference)

    def read_cake(self, reference: str) -> dict[str, Any]:
        return self._snapshot_and_cake(reference, include_candidates=False)[1]

    def _plate_context(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        return self.portfolio._trello_role("plate")

    def _plate_slice(self, reference: str) -> dict[str, Any]:
        plate_board, _ = self._plate_context()
        card = self.portfolio.trello.locate_card(reference)
        if card.get("idBoard") != plate_board["id"]:
            raise CakeError("A Trello canonical Slice must be a card on the configured Plate board")
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

    @staticmethod
    def _assert_parent(cake: dict[str, Any], record: dict[str, Any]) -> None:
        if not record.get("cake") or not _record_matches(cake, record["cake"]):
            raise CakeError("The Slice does not belong to the selected parent Cake")

    def read_slice(self, cake_reference: str, slice_reference: str) -> dict[str, Any]:
        snapshot, cake = self._snapshot_and_cake(cake_reference)
        record = self.portfolio._candidate_record(snapshot, slice_reference)
        self._assert_parent(cake, record)
        return record

    def preview_sync_index(self, cake_reference: str) -> dict[str, Any]:
        snapshot, cake = self._snapshot_and_cake(cake_reference)
        provider, _ = self._provider(cake)
        self._assert_registry_available(snapshot, cake)
        records = [
            item
            for item in snapshot.get("slice_catalog", [])
            if item.get("adapter") == provider
            and item.get("cake")
            and _record_matches(cake, item["cake"])
        ]
        by_reference = {_slice_ref(item): item for item in records}
        existing = [
            value
            for value in cake.get("slice_index") or []
            if any(canonical_ref(value) == canonical_ref(reference) for reference in by_reference)
        ]
        existing_keys = {canonical_ref(value) for value in existing}
        missing = sorted(
            (
                reference
                for reference in by_reference
                if canonical_ref(reference) not in existing_keys
            ),
            key=lambda reference: (
                normalize(by_reference[reference].get("name", "")),
                normalize(reference),
            ),
        )
        target_index = [*existing, *missing]
        write = {
            "action": "sync_cake_slice_index",
            "cake": _card_ref(cake),
            "slice_index": target_index,
            "target_body": _cake_body(cake, slice_index=target_index),
        }
        payload = {
            "operation": "sync_slice_index",
            "parent": _parent_state(cake),
            "write": write,
        }
        return {"status": "preview", "confirmation_token": token_for(payload), **payload}

    def sync_index(
        self, cake_reference: str, *, confirmation_token: str | None = None
    ) -> dict[str, Any]:
        preview = self.preview_sync_index(cake_reference)
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the Cake or its Slice Registry changed")
        self.portfolio._update_cake(
            preview["parent"], slice_index=preview["write"]["slice_index"]
        )
        return {
            "status": "synced",
            "cake": preview["write"]["cake"],
            "slice_index": preview["write"]["slice_index"],
        }

    @staticmethod
    def _target(
        cake: dict[str, Any],
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None,
        disposition: str,
        plate: str | None = None,
    ) -> dict[str, str]:
        if not title.strip():
            raise CakeError("A Slice needs a title")
        return {
            "title": title.strip(),
            "body": format_slice_contract(
                _card_ref(cake),
                outcome,
                success,
                not_included,
                disposition=disposition,
                plate=plate,
            ),
        }

    @staticmethod
    def _provider(cake: dict[str, Any]) -> tuple[str, str | None]:
        repository = github_repository_name(cake.get("repository"))
        return ("github", repository) if repository else ("plate", None)

    @staticmethod
    def _assert_registry_available(snapshot: dict[str, Any], cake: dict[str, Any]) -> None:
        if any(
            canonical_ref(item.get("cake")) == canonical_ref(cake.get("url"))
            and item.get("relevance") == "slice_registry"
            and item.get("status") in {"unavailable", "unsupported"}
            for item in snapshot.get("source_health", [])
        ):
            raise CakeError("The Cake's Slice Registry is unavailable; the write cannot be checked safely")

    def preview_create(
        self,
        cake_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
    ) -> dict[str, Any]:
        snapshot, cake = self._snapshot_and_cake(cake_reference)
        provider, repository = self._provider(cake)
        self._assert_registry_available(snapshot, cake)

        target = self._target(
            cake,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            disposition="candidate",
        )
        if provider == "github":
            assert repository
            write = {
                "action": "create_github_slice_issue",
                "repository": repository,
                "label": SLICE_LABEL,
                **target,
            }
            placeholder = CREATED_GITHUB_SLICE_URL
        else:
            plate_board, lists = self._plate_context()
            write = {
                "action": "create_archived_plate_slice",
                "board": {"id": plate_board["id"], "name": plate_board.get("name")},
                "list": {"id": lists["eating"]["id"], "name": lists["eating"].get("name")},
                **target,
            }
            placeholder = CREATED_TRELLO_SLICE_URL

        target_index = _append_reference(list(cake.get("slice_index") or []), placeholder)
        cake_write = {
            "action": "append_to_cake_slice_index",
            "cake": _card_ref(cake),
            "slice_index": target_index,
            "target_body": _preview_cake_body(
                cake, provider=provider, slice_index=target_index
            ),
        }
        payload = {
            "operation": "create_slice",
            "provider": provider,
            "parent": _parent_state(cake),
            "write": write,
            "cake_write": cake_write,
        }
        return {"status": "preview", "confirmation_token": token_for(payload), **payload}

    def create(
        self,
        cake_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_create(
            cake_reference,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the parent, registry, or Slice draft changed")

        write = preview["write"]
        if preview["provider"] == "github":
            self.portfolio.github.ensure_label(write["repository"], write["label"])
            created = self.portfolio.github.create_issue(
                write["repository"],
                title=write["title"],
                body=write["body"],
                labels=[write["label"]],
            )
        else:
            created_card = self.portfolio.trello.create_card(
                write["list"]["id"],
                name=write["title"],
                description=write["body"],
            )
            try:
                created_card = self.portfolio.trello.update_card(created_card["id"], closed=True)
            except CakeError as exc:
                reference = created_card.get("url") or created_card.get("id")
                raise CakeError(
                    f"Slice {reference} was created but could not be archived; archive it before continuing. Cause: {exc}"
                ) from None
            created = {
                "id": created_card["id"],
                "url": created_card.get("url") or created_card["id"],
                "name": created_card.get("name", write["title"]),
                "adapter": "plate",
                "canonical_state": "archived",
                **parse_slice_contract(created_card.get("desc", write["body"])),
            }

        created_reference = _slice_ref(created)
        cake = preview["parent"]
        target_index = _append_reference(
            [
                value
                for value in preview["cake_write"]["slice_index"]
                if value not in {CREATED_GITHUB_SLICE_URL, CREATED_TRELLO_SLICE_URL}
            ],
            created_reference,
        )
        try:
            self.portfolio._update_cake(cake, slice_index=target_index)
        except CakeError as exc:
            raise CakeError(
                f"Slice {created_reference} was created, but its Cake index was not updated; reconcile the Cake card before continuing. Cause: {exc}"
            ) from None
        return {"status": "created", "slice": created, "cake_slice_index": target_index}

    def preview_update(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
    ) -> dict[str, Any]:
        snapshot, cake = self._snapshot_and_cake(cake_reference)
        current = self.portfolio._candidate_record(snapshot, slice_reference)
        self._assert_parent(cake, current)
        disposition = normalize(current.get("disposition", "candidate")) or "candidate"
        if disposition in TERMINAL_SLICE_DISPOSITIONS:
            raise CakeError("A Finished or Abandoned Slice cannot be reshaped")
        target = self._target(
            cake,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            disposition=disposition,
            plate=current.get("plate") if current.get("adapter") == "github" else None,
        )
        write = {
            "action": "update_github_slice_issue"
            if current.get("adapter") == "github"
            else "update_plate_slice",
            "slice": _slice_ref(current),
            **target,
        }
        payload = {
            "operation": "update_slice",
            "parent": _parent_state(cake),
            "source": current,
            "write": write,
        }
        return {"status": "preview", "confirmation_token": token_for(payload), **payload}

    def update(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_update(
            cake_reference,
            slice_reference,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the parent, Slice, or draft changed")
        source = preview["source"]
        write = preview["write"]
        if source.get("adapter") == "github":
            updated = self.portfolio.github.update_issue(
                write["slice"], title=write["title"], body=write["body"]
            )
        else:
            card = self.portfolio.trello.update_card(
                source["id"], name=write["title"], description=write["body"]
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

    def preview_adopt(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
    ) -> dict[str, Any]:
        _, cake = self._snapshot_and_cake(cake_reference)
        if github_repository_name(cake.get("repository")):
            raise CakeError("A repository-backed Cake cannot adopt a Trello card as a canonical Slice")
        current = self._plate_slice(slice_reference)
        if current.get("cake"):
            raise CakeError("Adopt only repairs a parentless Slice; it cannot reparent an existing Slice")
        disposition = "current" if current.get("canonical_state") == "open" else "candidate"
        target = self._target(
            cake,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
            disposition=disposition,
        )
        target_index = _append_reference(
            list(cake.get("slice_index") or []), _card_ref(current)
        )
        payload = {
            "operation": "adopt_slice",
            "parent": _parent_state(cake),
            "source": current,
            "write": {
                "action": "adopt_parentless_plate_slice",
                "slice": _card_ref(current),
                **target,
            },
            "cake_write": {
                "action": "append_to_cake_slice_index",
                "cake": _card_ref(cake),
                "slice_index": target_index,
                "target_body": _cake_body(cake, slice_index=target_index),
            },
        }
        return {"status": "preview", "confirmation_token": token_for(payload), **payload}

    def adopt(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        title: str,
        outcome: str,
        success: str,
        not_included: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_adopt(
            cake_reference,
            slice_reference,
            title=title,
            outcome=outcome,
            success=success,
            not_included=not_included,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the parent, Slice, or draft changed")
        source = preview["source"]
        write = preview["write"]
        card = self.portfolio.trello.update_card(
            source["id"], name=write["title"], description=write["body"]
        )
        self.portfolio._update_cake(
            preview["parent"], slice_index=preview["cake_write"]["slice_index"]
        )
        adopted = {
            "id": card["id"],
            "url": card.get("url") or card["id"],
            "name": card.get("name", write["title"]),
            "adapter": "plate",
            "canonical_state": "archived" if card.get("closed") else "open",
            **parse_slice_contract(card.get("desc", write["body"])),
        }
        return {"status": "adopted", "slice": adopted}

    def preview_migrate_to_github(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        repository: str,
    ) -> dict[str, Any]:
        snapshot, cake = self._snapshot_and_cake(cake_reference)
        repository_name = github_repository_name(repository)
        if not repository_name:
            raise CakeError("Migration needs a GitHub repository URL or owner/repository")
        existing_repository = github_repository_name(cake.get("repository"))
        if existing_repository and existing_repository.casefold() != repository_name.casefold():
            raise CakeError("The Cake already uses a different GitHub Slice repository")
        source = self.portfolio._candidate_record(snapshot, slice_reference)
        self._assert_parent(cake, source)
        if source.get("adapter") != "plate":
            raise CakeError("Only a Trello canonical Slice can be migrated to GitHub")
        if source.get("canonical_state") != "archived":
            raise CakeError("Only an inactive archived Slice can be migrated; exit current work first")
        other_trello = [
            item
            for item in snapshot.get("slice_catalog", [])
            if item is not source
            and item.get("adapter") == "plate"
            and item.get("cake")
            and _record_matches(cake, item["cake"])
        ]
        if other_trello:
            raise CakeError("Migrate all of this Cake's Trello Slices together before changing its registry")

        disposition = normalize(source.get("disposition", "candidate")) or "candidate"
        if disposition in TERMINAL_SLICE_DISPOSITIONS:
            raise CakeError("A terminal Slice does not need canonical-registry migration")
        target = self._target(
            cake,
            title=source.get("name") or "",
            outcome=source.get("outcome") or "",
            success=source.get("success") or "",
            not_included=source.get("not_included"),
            disposition=disposition,
        )
        existing_github = [
            item
            for item in self.portfolio.github.slices(repository_name)
            if item.get("cake") and _record_matches(cake, item["cake"])
        ]
        existing_refs = [_slice_ref(item) for item in existing_github]
        target_index = _append_reference(existing_refs, CREATED_GITHUB_SLICE_URL)
        target_next = (
            CREATED_GITHUB_SLICE_URL
            if canonical_ref(cake.get("next_slice")) == canonical_ref(_slice_ref(source))
            else cake.get("next_slice")
        )
        migration_dummy = "https://github.com/cake/migrated-slice/issues/0"
        migrated_body = format_plate_projection_contract(
            migration_dummy,
            _card_ref(cake),
            disposition="migrated",
        ).replace(migration_dummy, CREATED_GITHUB_SLICE_URL)
        payload = {
            "operation": "migrate_slice_to_github",
            "parent": _parent_state(cake),
            "source": source,
            "writes": [
                {
                    "action": "create_github_slice_issue",
                    "repository": repository_name,
                    "label": SLICE_LABEL,
                    **target,
                },
                {
                    "action": "supersede_trello_slice",
                    "slice": _card_ref(source),
                    "target_body": migrated_body,
                    "closed": True,
                },
                {
                    "action": "set_cake_slice_registry",
                    "cake": _card_ref(cake),
                    "repository": github_repository_url(repository_name),
                    "slice_index": target_index,
                    "next_slice": target_next,
                    "target_body": _preview_cake_body(
                        cake,
                        provider="github",
                        repository=repository_name,
                        slice_index=target_index,
                        next_slice=target_next,
                    ),
                },
            ],
        }
        return {"status": "preview", "confirmation_token": token_for(payload), **payload}

    def migrate_to_github(
        self,
        cake_reference: str,
        slice_reference: str,
        *,
        repository: str,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_migrate_to_github(
            cake_reference, slice_reference, repository=repository
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the Cake, source Slice, or repository changed")
        create_write, source_write, cake_write = preview["writes"]
        self.portfolio.github.ensure_label(create_write["repository"], create_write["label"])
        created = self.portfolio.github.create_issue(
            create_write["repository"],
            title=create_write["title"],
            body=create_write["body"],
            labels=[create_write["label"]],
        )
        created_reference = _slice_ref(created)
        superseded_body = source_write["target_body"].replace(
            CREATED_GITHUB_SLICE_URL, created_reference
        )
        self.portfolio.trello.update_card(
            preview["source"]["id"], description=superseded_body, closed=True
        )
        target_index = [
            created_reference if value == CREATED_GITHUB_SLICE_URL else value
            for value in cake_write["slice_index"]
        ]
        next_slice = (
            created_reference
            if cake_write.get("next_slice") == CREATED_GITHUB_SLICE_URL
            else cake_write.get("next_slice")
        )
        self.portfolio._update_cake(
            preview["parent"],
            repository=cake_write["repository"],
            slice_index=target_index,
            next_slice=next_slice,
        )
        return {
            "status": "migrated",
            "slice": created,
            "superseded_trello_slice": _slice_ref(preview["source"]),
            "cake_slice_index": target_index,
        }
