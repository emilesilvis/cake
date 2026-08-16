"""Deep portfolio module shared by cake-prioritise and cake-slice."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .config import CONFIG_PATH, config_status, load_config, normalized_config
from .capacity import (
    observe_rhythms,
    rhythm_checklist_plan,
)
from .domain import (
    CakeError,
    available_slice_references,
    canonical_ref,
    format_cake_contract,
    format_plate_projection_contract,
    format_slice_contract,
    github_repository_name,
    is_github_issue_url,
    normalize,
    parse_cake_contract,
    parse_plate_projection_contract,
    parse_slice_contract,
    previous_slice_reference,
    preview_transition,
    token_for,
    trello_card_url,
    validate_snapshot,
)
from .providers import GitHubAdapter, TrelloAdapter


def _card_ref(card: dict[str, Any]) -> str:
    short_link = card.get("shortLink") or card.get("raw", {}).get("shortLink")
    if short_link:
        return f"https://trello.com/c/{short_link}"
    return trello_card_url(card.get("url") or card["id"])


def _slice_ref(record: dict[str, Any]) -> str:
    reference = record.get("url") or record.get("id")
    if record.get("adapter") == "github" and is_github_issue_url(reference):
        return str(reference).rstrip("/")
    return _card_ref(record)


def _plate_ref(record: dict[str, Any]) -> str:
    return trello_card_url(record.get("plate_card") or record.get("url") or record["id"])


def _compact_card(card: dict[str, Any]) -> dict[str, Any]:
    return {
        key: card.get(key)
        for key in (
            "id",
            "name",
            "desc",
            "url",
            "closed",
            "idBoard",
            "idList",
            "pos",
            "shortLink",
            "due",
            "dueComplete",
            "labels",
            "dateLastActivity",
        )
    }


def _cake_from_card(card: dict[str, Any], state: str) -> dict[str, Any]:
    return {
        "id": card["id"],
        "url": card.get("url") or card["id"],
        "name": card.get("name", ""),
        "state": state,
        "position": card.get("pos"),
        **parse_cake_contract(card.get("desc", "")),
        "current_slices": [],
        "raw": _compact_card(card),
    }


def _slice_from_trello(card: dict[str, Any], *, lane: str | None = None) -> dict[str, Any]:
    contract = parse_slice_contract(card.get("desc", ""))
    return {
        "id": card["id"],
        "url": card.get("url") or card["id"],
        "name": card.get("name", ""),
        "adapter": "plate",
        "canonical_state": "archived" if card.get("closed") else "open",
        "lane": lane,
        **contract,
        "raw": _compact_card(card),
    }


def _projection_from_trello(
    card: dict[str, Any], *, lane: str | None = None
) -> dict[str, Any] | None:
    contract = parse_plate_projection_contract(card.get("desc", ""))
    if not is_github_issue_url(contract.get("slice")):
        return None
    return {
        "id": card["id"],
        "url": card.get("url") or card["id"],
        "name": card.get("name", ""),
        "adapter": "github",
        "canonical_state": None,
        "lane": lane,
        "plate_card": card.get("url") or card["id"],
        "projection": True,
        **contract,
        "raw": _compact_card(card),
    }


def _record_matches(record: dict[str, Any], reference: str | None) -> bool:
    expected = canonical_ref(reference)
    return expected is not None and expected in {
        canonical_ref(record.get("id")),
        canonical_ref(record.get("url")),
        canonical_ref(record.get("slice")),
        canonical_ref(record.get("plate_card")),
    }


def _without_slice(values: list[str], reference: str | None) -> list[str]:
    key = canonical_ref(reference)
    return [value for value in values if canonical_ref(value) != key]


def _with_slice(values: list[str], reference: str) -> list[str]:
    return [*_without_slice(values, reference), reference]


class CakePortfolio:
    """Read, preview, and apply Cake portfolio transitions through injected adapters."""

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        config_path: Path = CONFIG_PATH,
        trello: TrelloAdapter | None = None,
        github: GitHubAdapter | None = None,
    ):
        raw_config = config if config is not None else load_config(config_path)
        self.config = normalized_config(raw_config)
        self.config_path = config_path
        self.trello = trello or TrelloAdapter()
        self.github = github or GitHubAdapter()

    def status(self) -> dict[str, Any]:
        return config_status(self.config, self.config_path)

    def _required_source(self, role: str) -> dict[str, Any]:
        source = self.config.get("portfolio", {}).get(role)
        if not isinstance(source, dict):
            raise CakeError(f"Cake configuration is missing the {role.replace('_', ' ')} source")
        if source.get("adapter") != "trello":
            raise CakeError(f"The current implementation does not support {source.get('adapter')!r} for {role}")
        if not isinstance(source.get("board"), str) or not source["board"].strip():
            raise CakeError(f"The configured {role.replace('_', ' ')} source needs a Trello board")
        return source

    def _trello_role(self, role: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        source = self._required_source(role)
        board = self.trello.board(source["board"])
        named_lists: dict[str, dict[str, Any]] = {}
        configured_lists = source.get("lists", {})
        if not isinstance(configured_lists, dict):
            raise CakeError(
                f"The configured {role.replace('_', ' ')} lists must be a JSON object"
            )
        required_states = {
            "cake_stand": {"on_stand", "parked", "finished"},
            "plate": {"eating", "blocked"},
        }.get(role, set())
        missing_states = required_states - set(configured_lists)
        if missing_states:
            raise CakeError(
                f"The configured {role.replace('_', ' ')} source is missing lists for "
                + ", ".join(sorted(missing_states))
            )
        for state, name in configured_lists.items():
            if not isinstance(name, str) or not name.strip():
                raise CakeError(
                    f"The configured {role.replace('_', ' ')} list for {state!r} is invalid"
                )
            named_lists[state] = self.trello.list(board, name)
        return board, named_lists

    def _rhythm_context(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        set[tuple[str, str]],
        list[dict[str, Any]],
        dict[str, list[dict[str, Any]]],
    ]:
        """Read Rhythm records and identify explicitly configured non-domain lists."""

        rhythms: list[dict[str, Any]] = []
        memberships: set[tuple[str, str]] = set()
        health: list[dict[str, Any]] = []
        rhythm_sources = self.config.get("portfolio", {}).get("rhythm_sources", [])
        for source in rhythm_sources:
            if not isinstance(source, dict) or source.get("adapter") != "trello":
                health.append(
                    {"source": source, "status": "unsupported", "relevance": "rhythms"}
                )
                continue
            if not isinstance(source.get("board"), str) or not source["board"].strip():
                health.append(
                    {
                        "source": source,
                        "status": "unavailable",
                        "relevance": "rhythms",
                        "error": "Rhythm source needs a Trello board",
                    }
                )
                continue
            configured_lists = source.get("lists", [])
            if not isinstance(configured_lists, list) or any(
                not isinstance(item, str) or not item.strip() for item in configured_lists
            ):
                health.append(
                    {
                        "source": source,
                        "status": "unavailable",
                        "relevance": "rhythms",
                        "error": "Rhythm source lists must be a JSON list of Trello list references",
                    }
                )
                continue
            try:
                board = self.trello.board(source["board"])
                cards = self.trello.cards(board)
                if configured_lists:
                    lists = [self.trello.list(board, item) for item in configured_lists]
                    allowed = {item["id"] for item in lists}
                    memberships.update((board["id"], list_id) for list_id in allowed)
                    cards = [card for card in cards if card.get("idList") in allowed]
                rhythms.extend(_compact_card(card) for card in cards)
            except CakeError as exc:
                health.append(
                    {
                        "source": source,
                        "status": "unavailable",
                        "relevance": "rhythms",
                        "error": str(exc),
                    }
                )
        checklists_by_card: dict[str, list[dict[str, Any]]] = {}
        for card in rhythms:
            try:
                checklists_by_card[card["id"]] = self.trello.checklists(card["id"])
            except CakeError as exc:
                health.append(
                    {
                        "source": card.get("url") or card["id"],
                        "status": "unavailable",
                        "relevance": "rhythm_checklist",
                        "error": str(exc),
                    }
                )
        return rhythms, memberships, health, checklists_by_card

    def snapshot(
        self,
        *,
        include_candidates: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        pantry_board, _ = self._trello_role("pantry")
        stand_board, stand_lists = self._trello_role("cake_stand")
        plate_board, plate_lists = self._trello_role("plate")

        pantry_cards = sorted(self.trello.cards(pantry_board), key=lambda card: card.get("pos", 0))
        all_stand_cards = sorted(
            self.trello.cards(stand_board, include_archived=True),
            key=lambda card: card.get("pos", 0),
        )
        stand_cards = [card for card in all_stand_cards if not card.get("closed")]
        visible_plate_cards = sorted(
            self.trello.cards(plate_board), key=lambda card: card.get("pos", 0)
        )
        all_plate_cards = self.trello.cards(plate_board, include_archived=True)
        (
            rhythms,
            rhythm_memberships,
            rhythm_health,
            rhythm_checklists,
        ) = self._rhythm_context()
        timezone_name = self.config.get("portfolio", {}).get("timezone")
        observed_at = now or datetime.now(timezone.utc)
        rhythms = observe_rhythms(
            rhythms,
            rhythm_checklists,
            now=observed_at,
            timezone_name=timezone_name,
        )

        def is_rhythm_card(card: dict[str, Any]) -> bool:
            return (card.get("idBoard"), card.get("idList")) in rhythm_memberships

        pantry_cards = [card for card in pantry_cards if not is_rhythm_card(card)]
        visible_plate_cards = [card for card in visible_plate_cards if not is_rhythm_card(card)]
        all_plate_cards = [card for card in all_plate_cards if not is_rhythm_card(card)]

        snapshot: dict[str, Any] = {
            "priority": self.config.get("portfolio", {}).get("priority"),
            "priority_needs_confirmation": True,
            "pantry": [_cake_from_card(card, "pantry") for card in pantry_cards],
            "cake_stand": {"on_stand": [], "parked": [], "finished": []},
            "archived_cakes": [],
            "plate": {"eating": [], "blocked": []},
            "slice_catalog": [],
            "rhythms": rhythms,
            "capacity": {},
            "source_health": rhythm_health,
            "unexpected_records": [],
            "sources": {
                "pantry": {
                    "id": pantry_board["id"],
                    "name": pantry_board["name"],
                    "url": pantry_board.get("url"),
                },
                "cake_stand": {
                    "id": stand_board["id"],
                    "name": stand_board["name"],
                    "url": stand_board.get("url"),
                    "lists": {
                        state: {"id": item["id"], "name": item.get("name")}
                        for state, item in stand_lists.items()
                    },
                },
                "plate": {
                    "id": plate_board["id"],
                    "name": plate_board["name"],
                    "url": plate_board.get("url"),
                    "lists": {
                        lane: {"id": item["id"], "name": item.get("name")}
                        for lane, item in plate_lists.items()
                    },
                },
            },
        }

        stand_state_by_list = {item["id"]: state for state, item in stand_lists.items()}
        for card in all_stand_cards:
            if not card.get("closed") or is_rhythm_card(card):
                continue
            former_state = stand_state_by_list.get(card.get("idList"))
            if former_state in {"on_stand", "parked", "finished"}:
                archived = _cake_from_card(card, "archived")
                archived["former_state"] = former_state
                snapshot["archived_cakes"].append(archived)

        for card in stand_cards:
            if is_rhythm_card(card):
                continue
            state = stand_state_by_list.get(card.get("idList"))
            if state not in {"on_stand", "parked", "finished"}:
                unexpected = {
                    "role": "cake_stand",
                    "reason": "card is in an unconfigured list",
                    "card": _compact_card(card),
                }
                snapshot["unexpected_records"].append(unexpected)
                snapshot["source_health"].append(
                    {
                        "source": card.get("url") or card["id"],
                        "status": "unavailable",
                        "relevance": "cake_stand_membership",
                        "error": unexpected["reason"],
                    }
                )
                continue
            snapshot["cake_stand"][state].append(_cake_from_card(card, state))

        plate_lane_by_list = {item["id"]: lane for lane, item in plate_lists.items()}
        for card in visible_plate_cards:
            lane = plate_lane_by_list.get(card.get("idList"))
            if lane not in {"eating", "blocked"}:
                unexpected = {
                    "role": "plate",
                    "reason": "visible card is in an unconfigured list",
                    "card": _compact_card(card),
                }
                snapshot["unexpected_records"].append(unexpected)
                snapshot["source_health"].append(
                    {
                        "source": card.get("url") or card["id"],
                        "status": "unavailable",
                        "relevance": "plate_membership",
                        "error": unexpected["reason"],
                    }
                )
                continue
            projection = _projection_from_trello(card, lane=lane)
            current = projection or {
                **_slice_from_trello(card, lane=lane),
                "plate_card": card.get("url") or card["id"],
                "slice": card.get("url") or card["id"],
                "projection": False,
                "disposition": "current",
            }
            snapshot["plate"][lane].append(current)

        catalog_by_ref: dict[str, dict[str, Any]] = {}

        def add_slice(slice_record: dict[str, Any]) -> None:
            key = canonical_ref(slice_record.get("url") or slice_record.get("id"))
            if key:
                catalog_by_ref[key] = slice_record

        for card in all_plate_cards:
            if _projection_from_trello(card):
                continue
            parsed = _slice_from_trello(card)
            if include_candidates or not card.get("closed"):
                add_slice(parsed)

        cakes = [
            *snapshot["pantry"],
            *snapshot["cake_stand"]["on_stand"],
            *snapshot["cake_stand"]["parked"],
            *snapshot["cake_stand"]["finished"],
            *snapshot["archived_cakes"],
        ]
        repository_cakes: dict[str, tuple[str, list[dict[str, Any]]]] = {}
        for cake in cakes:
            repository = github_repository_name(cake.get("repository"))
            if repository:
                key = repository.casefold()
                repository_cakes.setdefault(key, (repository, []))[1].append(cake)

        for repository, repository_parents in repository_cakes.values():
            try:
                github_slices = self.github.slices(repository)
            except CakeError as exc:
                for cake in repository_parents:
                    snapshot["source_health"].append(
                        {
                            "cake": cake.get("url") or cake.get("id"),
                            "source": f"https://github.com/{repository}/issues",
                            "status": "unavailable",
                            "relevance": "slice_registry",
                            "error": str(exc),
                        }
                    )
                continue
            for issue in github_slices:
                if issue.get("cake") and any(
                    _record_matches(cake, issue["cake"]) for cake in cakes
                ):
                    add_slice({**issue, "repository": repository})

        snapshot["slice_catalog"] = list(catalog_by_ref.values())
        catalog = snapshot["slice_catalog"]
        for cake in cakes:
            expected_adapter = "github" if github_repository_name(cake.get("repository")) else "plate"
            cake["slice_index"] = [
                _slice_ref(record)
                for record in catalog
                if record.get("adapter") == expected_adapter
                and record.get("cake")
                and _record_matches(cake, record["cake"])
            ]
        for lane in ("eating", "blocked"):
            for current in snapshot["plate"][lane]:
                canonical = next(
                    (item for item in catalog if _record_matches(item, current.get("slice"))), None
                )
                if canonical:
                    plate_state = {
                        key: current.get(key)
                        for key in (
                            "id",
                            "url",
                            "raw",
                            "lane",
                            "plate_card",
                            "slice",
                            "projection",
                        )
                    }
                    current.clear()
                    current.update(
                        {
                            **canonical,
                            **plate_state,
                            "disposition": "current",
                        }
                    )

        on_stand = snapshot["cake_stand"]["on_stand"]
        for lane in ("eating", "blocked"):
            for current in snapshot["plate"][lane]:
                parents = [cake for cake in on_stand if _record_matches(cake, current.get("cake"))]
                if len(parents) == 1:
                    parents[0]["current_slices"].append(
                        trello_card_url(current["plate_card"])
                    )
        for cake in on_stand:
            cake["condition"] = (
                "being_eaten" if cake["current_slices"] else "waiting_on_the_stand"
            )

        snapshot["capacity"] = {
            "cake_stand": {
                "count": len(on_stand),
                "policy_owner": "trello",
                "needs_current_policy_observation": True,
                **self.trello.plugin_status(stand_board),
            },
            "plate": {
                "count": len(snapshot["plate"]["eating"]) + len(snapshot["plate"]["blocked"]),
                "counts_by_lane": {
                    lane: len(snapshot["plate"][lane]) for lane in ("eating", "blocked")
                },
                "policy_owner": "trello",
                "needs_current_policy_observation": True,
                **self.trello.plugin_status(plate_board),
            },
            "rhythms": [
                {
                    "id": item.get("id"),
                    "url": item.get("url"),
                    "name": item.get("name"),
                    "supports": item.get("supports"),
                    "progress": item.get("progress"),
                }
                for item in rhythms
            ],
        }
        snapshot["issues"] = validate_snapshot(snapshot)
        return snapshot

    def preview_rhythm_sync(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Preview exact writes for all current-period Rhythm checklists."""

        rhythms, _, health, checklists_by_card = self._rhythm_context()
        failures = [
            item
            for item in health
            if item.get("status") in {"unavailable", "unsupported"}
        ]
        if failures:
            raise CakeError(
                "Rhythm checklist sync needs every configured Rhythm source; "
                f"{len(failures)} source read failed"
            )
        observed_at = now or datetime.now(timezone.utc)
        timezone_name = self.config.get("portfolio", {}).get("timezone")
        plans = [
            rhythm_checklist_plan(
                card,
                checklists_by_card.get(card["id"], []),
                now=observed_at,
                timezone_name=timezone_name,
            )
            for card in rhythms
        ]
        changes = [change for plan in plans for change in plan["changes"]]
        payload = {
            "operation": "sync_rhythm_checklists",
            "changes": changes,
        }
        result = {
            "status": "preview" if changes else "current",
            "plans": plans,
            "changes": changes,
        }
        if changes:
            result["confirmation_token"] = token_for(payload)
        return result

    def sync_rhythm_checklists(
        self,
        *,
        confirmation_token: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Apply a fresh, explicitly approved Rhythm checklist sync preview."""

        preview = self.preview_rhythm_sync(now=now)
        if preview["status"] == "current" or confirmation_token is None:
            return preview
        changes = preview["changes"]
        payload = {
            "operation": "sync_rhythm_checklists",
            "changes": changes,
        }
        if confirmation_token != token_for(payload):
            raise CakeError(
                "The approval is stale: a Rhythm contract, checklist, or period changed"
            )

        applied: list[dict[str, Any]] = []
        try:
            for change in changes:
                action = change["action"]
                if action == "create_checklist":
                    checklist = self.trello.create_checklist(
                        change["card"], name=change["name"]
                    )
                    for name in change["items"]:
                        self.trello.create_check_item(checklist["id"], name=name)
                elif action == "rename_checklist":
                    self.trello.update_checklist(change["checklist"], name=change["to"])
                elif action == "add_check_item":
                    self.trello.create_check_item(change["checklist"], name=change["name"])
                elif action == "update_check_item":
                    self.trello.update_check_item(
                        change["card"],
                        change["item"],
                        name=change["to"]["name"],
                        state=change["to"]["state"],
                    )
                elif action == "delete_check_item":
                    self.trello.delete_check_item(change["card"], change["item"])
                else:
                    raise CakeError(f"Unknown Rhythm checklist action {action!r}")
                applied.append(change)
        except CakeError as exc:
            raise CakeError(
                f"Rhythm checklist sync stopped after {len(applied)} of "
                f"{len(changes)} changes; re-read before retrying. Cause: {exc}"
            ) from None
        return {"status": "synced", "changes": applied}

    def preview(
        self,
        operations: list[dict[str, Any]],
        *,
        capacity_policies: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return preview_transition(self.snapshot(), operations, capacity_policies)

    def preview_create_cake(
        self,
        *,
        name: str,
        direction: str,
        pantry_list: str,
        finished_when: str | None = None,
        repository: str | None = None,
    ) -> dict[str, Any]:
        """Preview one mature Cake card in a named Pantry list."""

        if not isinstance(name, str) or not name.strip():
            raise CakeError("A Cake needs a name")
        if not isinstance(direction, str) or not direction.strip():
            raise CakeError("A mature Cake needs a Direction")
        if not isinstance(pantry_list, str) or not pantry_list.strip():
            raise CakeError("Choose a Pantry list for the Cake")
        if finished_when is not None and (
            not isinstance(finished_when, str) or not finished_when.strip()
        ):
            raise CakeError("Finished when must be non-empty text when supplied")

        clean_name = name.strip()
        snapshot = self.snapshot(include_candidates=False)
        stand = snapshot.get("cake_stand", {})
        existing = [
            *snapshot.get("pantry", []),
            *stand.get("on_stand", []),
            *stand.get("parked", []),
            *stand.get("finished", []),
        ]
        if any(normalize(cake.get("name", "")) == normalize(clean_name) for cake in existing):
            raise CakeError(f"A non-archived Cake named {clean_name!r} already exists")

        pantry_board = snapshot["sources"]["pantry"]
        target_list = self.trello.list(pantry_board, pantry_list)
        write = {
            "action": "create_pantry_cake",
            "board": {"id": pantry_board["id"], "name": pantry_board.get("name")},
            "list": {"id": target_list["id"], "name": target_list.get("name")},
            "title": clean_name,
            "body": format_cake_contract(
                direction.strip(),
                finished_when=finished_when.strip() if finished_when else None,
                repository=repository,
                trello_markdown=True,
            ),
        }
        payload = {"operation": "create_cake", "write": write}
        return {
            "status": "preview",
            "confirmation_token": token_for(payload),
            **payload,
        }

    def create_cake(
        self,
        *,
        name: str,
        direction: str,
        pantry_list: str,
        finished_when: str | None = None,
        repository: str | None = None,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_create_cake(
            name=name,
            direction=direction,
            pantry_list=pantry_list,
            finished_when=finished_when,
            repository=repository,
        )
        if confirmation_token is None:
            return preview
        if confirmation_token != preview["confirmation_token"]:
            raise CakeError("The approval is stale: the Pantry destination or Cake contract changed")

        write = preview["write"]
        created = self.trello.create_card(
            write["list"]["id"],
            name=write["title"],
            description=write["body"],
        )
        return {"status": "created", "cake": _cake_from_card(created, "pantry")}

    def apply(
        self,
        operations: list[dict[str, Any]],
        confirmation_token: str,
        *,
        capacity_policies: list[dict[str, Any]] | None = None,
        allow_capacity_overage: bool = False,
    ) -> dict[str, Any]:
        preview = self.preview(
            operations,
            capacity_policies=capacity_policies,
        )
        if preview["confirmation_token"] != confirmation_token:
            raise CakeError("The confirmation token is invalid or relevant source state changed")
        if preview["capacity_warnings"] and not allow_capacity_overage:
            raise CakeError(
                "This transition exceeds provider-owned capacity; explicitly allow the reviewed overage"
            )
        applied: list[dict[str, Any]] = []
        try:
            index = 0
            while index < len(operations):
                operation = operations[index]
                following = operations[index + 1] if index + 1 < len(operations) else None
                if (
                    operation.get("action") == "nominate"
                    and following
                    and following.get("action") == "pull"
                    and canonical_ref(operation.get("cake"))
                    == canonical_ref(following.get("cake"))
                ):
                    snapshot = self.snapshot()
                    cake = self._cake_record(snapshot, operation["cake"])
                    candidate = self._candidate_record(snapshot, operation["slice"])
                    self._pull_candidate(
                        cake,
                        candidate,
                        following.get("lane", "eating"),
                    )
                    applied.extend((operation, following))
                    index += 2
                    continue
                self._execute(operation)
                applied.append(operation)
                index += 1
        except CakeError as exc:
            raise CakeError(
                f"Transition stopped after {len(applied)} of {len(operations)} operations; "
                f"re-read sources and reconcile explicitly. Cause: {exc}"
            ) from None
        result = self.snapshot()
        return {"status": "applied", "operations": applied, "snapshot": result}

    def _cake_record(self, snapshot: dict[str, Any], reference: str) -> dict[str, Any]:
        cakes = [
            *snapshot.get("pantry", []),
            *snapshot.get("cake_stand", {}).get("on_stand", []),
            *snapshot.get("cake_stand", {}).get("parked", []),
            *snapshot.get("cake_stand", {}).get("finished", []),
        ]
        matches = [cake for cake in cakes if _record_matches(cake, reference)]
        if len(matches) != 1:
            raise CakeError(f"Expected exactly one Cake matching {reference!r}")
        return matches[0]

    def _current_record(self, snapshot: dict[str, Any], reference: str) -> dict[str, Any]:
        records = [*snapshot["plate"]["eating"], *snapshot["plate"]["blocked"]]
        matches = [record for record in records if _record_matches(record, reference)]
        if len(matches) != 1:
            raise CakeError(f"Expected exactly one Plate Slice matching {reference!r}")
        return matches[0]

    def _candidate_record(self, snapshot: dict[str, Any], reference: str) -> dict[str, Any]:
        matches = [item for item in snapshot["slice_catalog"] if _record_matches(item, reference)]
        if len(matches) != 1:
            raise CakeError(f"Expected exactly one canonical Slice matching {reference!r}")
        return matches[0]

    def _update_cake(self, cake: dict[str, Any], **changes: Any) -> None:
        values = {
            "direction": cake.get("direction"),
            "finished_when": cake.get("finished_when"),
            "repository": cake.get("repository"),
            "slice_index": cake.get("slice_index", []),
            "previous_slice": cake.get("previous_slice"),
            "next_slice": cake.get("next_slice"),
            "current_slices": cake.get("current_slices", []),
            "available_slices": cake.get("available_slices", []),
            **changes,
        }
        description = format_cake_contract(
            values["direction"],
            values.get("next_slice"),
            values.get("finished_when"),
            values.get("current_slices"),
            values.get("repository"),
            values.get("available_slices"),
            values.get("previous_slice"),
            trello_markdown=True,
        )
        self.trello.update_card(cake["id"], description=description)

    def _execute(self, operation: dict[str, Any]) -> None:
        action = operation["action"]
        snapshot = self.snapshot()
        if action == "nominate":
            cake = self._cake_record(snapshot, operation["cake"])
            candidate = self._candidate_record(snapshot, operation["slice"])
            candidate_reference = _slice_ref(candidate)
            available = list(cake.get("available_slices") or [])
            if cake.get("next_slice"):
                available = _with_slice(available, cake["next_slice"])
            self._update_cake(
                cake,
                next_slice=candidate_reference,
                available_slices=_without_slice(available, candidate_reference),
            )
            return

        if action == "pull":
            cake = self._cake_record(snapshot, operation["cake"])
            candidate = self._candidate_record(snapshot, cake["next_slice"])
            self._pull_candidate(
                cake,
                candidate,
                operation.get("lane", "eating"),
            )
            return

        if action == "exit":
            current = self._current_record(snapshot, operation["plate_slice"])
            parent = self._cake_record(snapshot, current["cake"])
            disposition = normalize(operation["disposition"])
            reason = operation.get("reason")
            candidate = self._candidate_record(snapshot, current.get("slice") or current["url"])
            candidate_reference = _slice_ref(candidate)
            description = format_slice_contract(
                _card_ref(parent),
                candidate["outcome"],
                candidate["success"],
                candidate.get("not_included"),
                disposition,
                reason,
                trello_markdown=candidate.get("adapter") != "github",
            )
            if candidate.get("adapter") == "github":
                self.github.update_issue(
                    _slice_ref(candidate),
                    title=candidate.get("name", ""),
                    body=description,
                )
                if disposition in {"finished", "abandoned"}:
                    self.github.close_issue(_slice_ref(candidate))
                self.trello.update_card(current["id"], closed=True)
            else:
                self.trello.update_card(candidate["id"], description=description, closed=True)

            remaining = [
                item
                for item in (*snapshot["plate"]["eating"], *snapshot["plate"]["blocked"])
                if item is not current and _record_matches(parent, item.get("cake"))
            ]
            remaining_refs = [_plate_ref(item) for item in remaining]
            available = list(parent.get("available_slices") or [])
            available = (
                _with_slice(available, candidate_reference)
                if disposition == "paused"
                else _without_slice(available, candidate_reference)
            )

            if operation.get("next_slice"):
                next_slice = self._candidate_record(snapshot, operation["next_slice"])
                next_reference = _slice_ref(next_slice)
                self._update_cake(
                    parent,
                    next_slice=next_reference,
                    current_slices=remaining_refs,
                    available_slices=_without_slice(available, next_reference),
                )
            elif operation.get("cake_state"):
                self._move_cake_card(
                    parent,
                    operation["cake_state"],
                    {
                        **operation,
                        "available_slices": available,
                        "previous_slice": (
                            candidate_reference
                            if normalize(operation["cake_state"]) == "parked"
                            else None
                        ),
                    },
                )
            else:
                self._update_cake(
                    parent,
                    next_slice=None,
                    current_slices=remaining_refs,
                    available_slices=available,
                )
            return

        if action == "move_cake":
            cake = self._cake_record(snapshot, operation["cake"])
            self._move_cake_card(cake, operation["to"], operation, snapshot=snapshot)
            return

        if action == "archive_cake":
            cake = self._cake_record(snapshot, operation["cake"])
            if cake.get("state") != "parked":
                raise CakeError("Only a Parked Cake can be archived")
            current = [
                item
                for item in (*snapshot["plate"]["eating"], *snapshot["plate"]["blocked"])
                if _record_matches(cake, item.get("cake"))
            ]
            if current:
                raise CakeError("A Cake with a current Slice cannot be archived")
            self.trello.update_card(cake["id"], closed=True)
            return

        if action == "reorder":
            collection = operation["collection"]
            records = (
                snapshot["cake_stand"]["on_stand"]
                if collection == "on_stand"
                else snapshot["plate"][collection]
            )
            matches = [record for record in records if _record_matches(record, operation["record"])]
            if len(matches) != 1:
                raise CakeError("Could not resolve the record to reorder")
            position = operation["position"]
            if position == 0:
                target_position: str | float = "top"
            elif position == len(records) - 1:
                target_position = "bottom"
            else:
                without = [record for record in records if record is not matches[0]]
                previous = without[position - 1].get("position", without[position - 1]["raw"].get("pos"))
                following = without[position].get("position", without[position]["raw"].get("pos"))
                target_position = (float(previous) + float(following)) / 2
            target_id = matches[0]["id"]
            self.trello.update_card(target_id, position=target_position)
            return

        raise CakeError(f"Unknown transition action {action!r}")

    def _pull_candidate(
        self,
        cake: dict[str, Any],
        candidate: dict[str, Any],
        lane: str,
    ) -> None:
        _, plate_lists = self._trello_role("plate")
        target_list = plate_lists[normalize(lane).replace(" ", "_")]
        if candidate.get("adapter") == "github":
            if candidate.get("canonical_state") == "closed":
                self.github.reopen_issue(_slice_ref(candidate))
            projection = self.trello.create_card(
                target_list["id"],
                name=candidate.get("name", ""),
                description=format_plate_projection_contract(
                    _slice_ref(candidate), _card_ref(cake), trello_markdown=True
                ),
            )
            plate_reference = _card_ref(projection)
            description = format_slice_contract(
                _card_ref(cake),
                candidate["outcome"],
                candidate["success"],
                candidate.get("not_included"),
                "current",
                plate=plate_reference,
            )
            self.github.update_issue(
                _slice_ref(candidate),
                title=candidate.get("name", ""),
                body=description,
            )
        else:
            description = format_slice_contract(
                _card_ref(cake),
                candidate["outcome"],
                candidate["success"],
                candidate.get("not_included"),
                "current",
                trello_markdown=True,
            )
            updated = self.trello.update_card(
                candidate["id"],
                description=description,
                list_id=target_list["id"],
                closed=False,
            )
            plate_reference = _card_ref(updated) if updated.get("url") else _card_ref(candidate)
        available = list(cake.get("available_slices") or [])
        if cake.get("next_slice"):
            available = _with_slice(available, cake["next_slice"])
        self._update_cake(
            cake,
            next_slice=None,
            current_slices=[*cake.get("current_slices", []), plate_reference],
            available_slices=_without_slice(available, _slice_ref(candidate)),
        )

    def _move_cake_card(
        self,
        cake: dict[str, Any],
        target: str,
        operation: dict[str, Any],
        *,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        target = normalize(target).replace(" ", "_")
        stand_board, stand_lists = self._trello_role("cake_stand")
        changes: dict[str, Any] = {}
        if target == "pantry":
            raise CakeError("Mature Cakes do not return to Pantry; Park them instead")
        if target not in stand_lists:
            raise CakeError(f"Cake Stand has no configured {target!r} state")
        values = {
            "direction": operation.get("direction", cake.get("direction")),
            "finished_when": operation.get("finished_when", cake.get("finished_when")),
            "repository": cake.get("repository"),
            "slice_index": cake.get("slice_index", []),
            "previous_slice": operation.get(
                "previous_slice", cake.get("previous_slice")
            ),
            "next_slice": operation.get("next_slice", cake.get("next_slice")),
            "current_slices": cake.get("current_slices", []),
            "available_slices": operation.get(
                "available_slices", cake.get("available_slices", [])
            ),
        }
        if target == "parked":
            if values.get("next_slice"):
                values["available_slices"] = _with_slice(
                    list(values.get("available_slices") or []), values["next_slice"]
                )
            values["next_slice"] = None
            values["current_slices"] = []
            if not values.get("previous_slice"):
                source = snapshot or self.snapshot()
                values["previous_slice"] = previous_slice_reference(
                    {**cake, "state": "parked", "previous_slice": None},
                    source.get("slice_catalog", []),
                )
        elif target == "finished":
            values["previous_slice"] = None
            values["next_slice"] = None
            values["current_slices"] = []
            values["available_slices"] = []
        elif target == "on_stand":
            values["previous_slice"] = None
            source = snapshot or self.snapshot()
            current = [
                item
                for item in (*source["plate"]["eating"], *source["plate"]["blocked"])
                if _record_matches(cake, item.get("cake"))
            ]
            if current:
                values["current_slices"] = [_plate_ref(item) for item in current]
                values["next_slice"] = None
            elif operation.get("next_slice"):
                candidate = self._candidate_record(source, operation["next_slice"])
                values["next_slice"] = _slice_ref(candidate)
            if values.get("next_slice"):
                values["available_slices"] = _without_slice(
                    list(values.get("available_slices") or []), values["next_slice"]
                )
            if cake.get("state") == "finished":
                values["available_slices"] = available_slice_references(
                    {
                        **cake,
                        "state": "on_stand",
                        "next_slice": values.get("next_slice"),
                        "available_slices": values.get("available_slices", []),
                    },
                    source.get("slice_catalog", []),
                    current_references=(
                        str(item.get("slice") or item.get("url") or item.get("id"))
                        for item in current
                    ),
                )
        changes["description"] = format_cake_contract(
            values["direction"],
            values.get("next_slice"),
            values.get("finished_when"),
            values.get("current_slices"),
            values.get("repository"),
            values.get("available_slices"),
            values.get("previous_slice"),
            trello_markdown=True,
        )
        changes["board_id"] = stand_board["id"]
        changes["list_id"] = stand_lists[target]["id"]
        self.trello.update_card(cake["id"], **changes)
def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
