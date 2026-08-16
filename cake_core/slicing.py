"""Shape and safely write one provider-aware canonical Cake Slice."""

from __future__ import annotations

from typing import Any

from .domain import (
    CakeError,
    TERMINAL_SLICE_DISPOSITIONS,
    available_slice_references,
    canonical_ref,
    format_cake_contract,
    format_plate_projection_contract,
    format_slice_contract,
    github_repository_name,
    github_repository_url,
    normalize,
    previous_slice_reference,
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
            "previous_slice",
            "next_slice",
            "available_slices",
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
    available_slices: list[str] | None = None,
    next_slice: str | None | object = ...,
    previous_slice: str | None | object = ...,
) -> str:
    effective_next = cake.get("next_slice") if next_slice is ... else next_slice
    effective_previous = (
        cake.get("previous_slice") if previous_slice is ... else previous_slice
    )
    return format_cake_contract(
        cake.get("direction") or "",
        effective_next if isinstance(effective_next, str) else None,
        cake.get("finished_when"),
        cake.get("current_slices", []),
        repository if repository is not None else cake.get("repository"),
        available_slices
        if available_slices is not None
        else list(cake.get("available_slices") or []),
        effective_previous if isinstance(effective_previous, str) else None,
        trello_markdown=True,
    )


def _preview_cake_body(
    cake: dict[str, Any],
    *,
    provider: str,
    available_slices: list[str],
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
        available_slices=[
            dummy if value == placeholder else value for value in available_slices
        ],
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

    def preview_sync_available(self, cake_reference: str) -> dict[str, Any]:
        snapshot, cake = self._snapshot_and_cake(cake_reference)
        self._assert_registry_available(snapshot, cake)
        current_references = [
            item.get("slice") or item.get("url") or item.get("id")
            for item in (
                *snapshot.get("plate", {}).get("eating", []),
                *snapshot.get("plate", {}).get("blocked", []),
            )
            if item.get("cake") and _record_matches(cake, item["cake"])
        ]
        target_available = available_slice_references(
            cake,
            snapshot.get("slice_catalog", []),
            current_references=(str(value) for value in current_references if value),
        )
        target_previous = previous_slice_reference(
            cake, snapshot.get("slice_catalog", [])
        )
        write = {
            "action": "sync_cake_available_slices",
            "cake": _card_ref(cake),
            "available_slices": target_available,
            "previous_slice": target_previous,
            "target_body": _cake_body(
                cake,
                available_slices=target_available,
                previous_slice=target_previous,
            ),
        }
        payload = {
            "operation": "sync_available_slices",
            "parent": _parent_state(cake),
            "write": write,
        }
        return {"status": "preview", "confirmation_token": token_for(payload), **payload}

    def sync_available(
        self, cake_reference: str, *, confirmation_token: str | None = None
    ) -> dict[str, Any]:
        preview = self.preview_sync_available(cake_reference)
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the Cake or its Slices changed")
        self.portfolio._update_cake(
            preview["parent"],
            available_slices=preview["write"]["available_slices"],
            previous_slice=preview["write"]["previous_slice"],
        )
        return {
            "status": "synced",
            "cake": preview["write"]["cake"],
            "available_slices": preview["write"]["available_slices"],
            "previous_slice": preview["write"]["previous_slice"],
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
        trello_markdown: bool = False,
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
                trello_markdown=trello_markdown,
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
            raise CakeError("The Cake's Slices could not be read, so the write cannot be checked safely")

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
            trello_markdown=provider == "plate",
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

        target_available = _append_reference(
            list(cake.get("available_slices") or []), placeholder
        )
        cake_write = {
            "action": "add_available_slice",
            "cake": _card_ref(cake),
            "available_slices": target_available,
            "target_body": _preview_cake_body(
                cake, provider=provider, available_slices=target_available
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
        target_available = _append_reference(
            [
                value
                for value in preview["cake_write"]["available_slices"]
                if value not in {CREATED_GITHUB_SLICE_URL, CREATED_TRELLO_SLICE_URL}
            ],
            created_reference,
        )
        try:
            self.portfolio._update_cake(cake, available_slices=target_available)
        except CakeError as exc:
            raise CakeError(
                f"Slice {created_reference} was created, but its Cake was not updated; reconcile the Cake card before continuing. Cause: {exc}"
            ) from None
        return {
            "status": "created",
            "slice": created,
            "cake_available_slices": target_available,
        }

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
            trello_markdown=current.get("adapter") != "github",
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
            trello_markdown=True,
        )
        target_available = list(cake.get("available_slices") or [])
        if disposition == "candidate":
            target_available = _append_reference(target_available, _card_ref(current))
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
                "action": "update_available_slices",
                "cake": _card_ref(cake),
                "available_slices": target_available,
                "target_body": _cake_body(
                    cake, available_slices=target_available
                ),
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
            preview["parent"],
            available_slices=preview["cake_write"]["available_slices"],
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
        source_is_next = canonical_ref(cake.get("next_slice")) == canonical_ref(
            _slice_ref(source)
        )
        target_next = CREATED_GITHUB_SLICE_URL if source_is_next else cake.get("next_slice")
        target_cake = {
            **cake,
            "repository": github_repository_url(repository_name),
            "available_slices": [],
        }
        target_available = available_slice_references(target_cake, existing_github)
        if not source_is_next:
            target_available = _append_reference(
                target_available, CREATED_GITHUB_SLICE_URL
            )
        migration_dummy = "https://github.com/cake/migrated-slice/issues/0"
        migrated_body = format_plate_projection_contract(
            migration_dummy,
            _card_ref(cake),
            disposition="migrated",
            trello_markdown=True,
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
                    "action": "set_cake_slice_provider",
                    "cake": _card_ref(cake),
                    "repository": github_repository_url(repository_name),
                    "available_slices": target_available,
                    "next_slice": target_next,
                    "target_body": _preview_cake_body(
                        cake,
                        provider="github",
                        repository=repository_name,
                        available_slices=target_available,
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
        available_slices = [
            created_reference if value == CREATED_GITHUB_SLICE_URL else value
            for value in cake_write["available_slices"]
        ]
        next_slice = (
            created_reference
            if cake_write.get("next_slice") == CREATED_GITHUB_SLICE_URL
            else cake_write.get("next_slice")
        )
        self.portfolio._update_cake(
            preview["parent"],
            repository=cake_write["repository"],
            available_slices=available_slices,
            next_slice=next_slice,
        )
        return {
            "status": "migrated",
            "slice": created,
            "superseded_trello_slice": _slice_ref(preview["source"]),
            "cake_available_slices": available_slices,
        }
