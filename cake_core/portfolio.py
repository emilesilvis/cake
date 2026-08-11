"""Deep portfolio module shared by cake-prioritise and cake-slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import CONFIG_PATH, config_status, load_config, normalized_config
from .domain import (
    CakeError,
    canonical_ref,
    format_cake_contract,
    format_slice_contract,
    normalize,
    parse_cake_contract,
    parse_slice_contract,
    parse_slice_source,
    preview_transition,
    validate_snapshot,
)
from .providers import GitHubAdapter, TrelloAdapter, is_github_issue


def _card_ref(card: dict[str, Any]) -> str:
    return card.get("url") or card["id"]


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


def _record_matches(record: dict[str, Any], reference: str | None) -> bool:
    expected = canonical_ref(reference)
    return expected is not None and expected in {
        canonical_ref(record.get("id")),
        canonical_ref(record.get("url")),
        canonical_ref(record.get("slice")),
    }


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

    def _slice_by_reference(
        self,
        reference: str,
        plate_cards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if is_github_issue(reference):
            return self.github.issue(reference)
        matches = [card for card in plate_cards if _record_matches(card, reference)]
        if len(matches) == 1:
            return _slice_from_trello(matches[0])
        raise CakeError(f"No canonical Slice matches {reference!r}")

    def snapshot(self, *, include_candidates: bool = True) -> dict[str, Any]:
        pantry_board, _ = self._trello_role("pantry")
        stand_board, stand_lists = self._trello_role("cake_stand")
        plate_board, plate_lists = self._trello_role("plate")

        pantry_cards = sorted(self.trello.cards(pantry_board), key=lambda card: card.get("pos", 0))
        stand_cards = sorted(self.trello.cards(stand_board), key=lambda card: card.get("pos", 0))
        visible_plate_cards = sorted(
            self.trello.cards(plate_board), key=lambda card: card.get("pos", 0)
        )
        all_plate_cards = self.trello.cards(plate_board, include_archived=True)

        snapshot: dict[str, Any] = {
            "priority": self.config.get("portfolio", {}).get("priority"),
            "priority_needs_confirmation": True,
            "pantry": [_cake_from_card(card, "pantry") for card in pantry_cards],
            "cake_stand": {"on_stand": [], "parked": [], "finished": []},
            "plate": {"eating": [], "blocked": []},
            "slice_catalog": [],
            "capacity_constraints": [],
            "capacity": {},
            "source_health": [],
            "unexpected_records": [],
            "sources": {
                "pantry": {"id": pantry_board["id"], "name": pantry_board["name"], "url": pantry_board.get("url")},
                "cake_stand": {"id": stand_board["id"], "name": stand_board["name"], "url": stand_board.get("url")},
                "plate": {"id": plate_board["id"], "name": plate_board["name"], "url": plate_board.get("url")},
            },
        }

        stand_state_by_list = {item["id"]: state for state, item in stand_lists.items()}
        for card in stand_cards:
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
        external_refs: list[tuple[str, str | None]] = []
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
            contract = parse_slice_contract(card.get("desc", ""))
            canonical_reference = contract.get("cake") and _reference_field(card.get("desc", ""), "Slice")
            if canonical_reference:
                current = {
                    "id": card["id"],
                    "url": card.get("url") or card["id"],
                    "name": card.get("name", ""),
                    "plate_card": card.get("url") or card["id"],
                    "cake": contract.get("cake"),
                    "slice": canonical_reference,
                    "adapter": "proxy",
                    "canonical_on_plate": False,
                    "lane": lane,
                    "raw": _compact_card(card),
                }
                external_refs.append((canonical_reference, contract.get("cake")))
            else:
                current = {
                    **_slice_from_trello(card, lane=lane),
                    "plate_card": card.get("url") or card["id"],
                    "slice": card.get("url") or card["id"],
                    "canonical_on_plate": True,
                }
            snapshot["plate"][lane].append(current)

        catalog_by_ref: dict[str, dict[str, Any]] = {}

        def add_slice(slice_record: dict[str, Any]) -> None:
            key = canonical_ref(slice_record.get("url") or slice_record.get("id"))
            if key:
                catalog_by_ref[key] = slice_record

        for card in all_plate_cards:
            parsed = _slice_from_trello(card)
            if parsed.get("cake") and parsed.get("outcome") and parsed.get("success"):
                add_slice(parsed)

        cake_sources: dict[str, dict[str, Any]] = {}
        github_membership: dict[str, set[str]] = {}
        for cake in snapshot["cake_stand"]["on_stand"]:
            cake_key = canonical_ref(cake["url"])
            assert cake_key
            source_value = cake.get("slice_source")
            if not source_value:
                continue
            source: dict[str, Any] | None = None
            try:
                source = parse_slice_source(source_value)
                cake_sources[cake_key] = source
                if include_candidates and source["adapter"] == "github":
                    membership: set[str] = set()
                    for candidate in self.github.slices(
                        source["repository"], source.get("query", "")
                    ):
                        add_slice(candidate)
                        reference = canonical_ref(candidate.get("url") or candidate.get("id"))
                        if reference:
                            membership.add(reference)
                    github_membership[cake_key] = membership
                snapshot["source_health"].append(
                    {"cake": cake["url"], "source": source_value, "status": "available"}
                )
            except CakeError as exc:
                snapshot["source_health"].append(
                    {"cake": cake["url"], "source": source_value, "status": "unavailable", "error": str(exc)}
                )

            next_slice = cake.get("next_slice")
            next_key = canonical_ref(next_slice)
            if next_slice and canonical_ref(next_slice) not in catalog_by_ref:
                try:
                    add_slice(self._slice_by_reference(next_slice, all_plate_cards))
                except CakeError as exc:
                    snapshot["source_health"].append(
                        {
                            "cake": cake["url"],
                            "source": next_slice,
                            "status": "unavailable",
                            "relevance": "next_slice",
                            "error": str(exc),
                        }
                    )
            if (
                next_slice
                and source
                and source.get("adapter") == "github"
                and cake_key in github_membership
                and next_key not in github_membership[cake_key]
            ):
                snapshot["source_health"].append(
                    {
                        "cake": cake["url"],
                        "source": next_slice,
                        "status": "drift",
                        "relevance": "next_slice",
                        "error": "Next Slice is outside the Cake's configured GitHub query",
                    }
                )

        on_stand = snapshot["cake_stand"]["on_stand"]
        for reference, parent_reference in external_refs:
            if canonical_ref(reference) not in catalog_by_ref:
                try:
                    add_slice(self._slice_by_reference(reference, all_plate_cards))
                except CakeError as exc:
                    snapshot["source_health"].append(
                        {
                            "source": reference,
                            "status": "unavailable",
                            "relevance": "current_slice",
                            "error": str(exc),
                        }
                    )
            parents = [
                cake for cake in on_stand if _record_matches(cake, parent_reference)
            ]
            if len(parents) != 1:
                continue
            parent_key = canonical_ref(parents[0]["url"])
            source = cake_sources.get(parent_key or "")
            if (
                source
                and source.get("adapter") == "github"
                and parent_key in github_membership
                and canonical_ref(reference) not in github_membership[parent_key]
            ):
                snapshot["source_health"].append(
                    {
                        "cake": parents[0]["url"],
                        "source": reference,
                        "status": "drift",
                        "relevance": "current_slice",
                        "error": "Current Slice is outside the Cake's configured GitHub query",
                    }
                )

        snapshot["slice_catalog"] = list(catalog_by_ref.values())
        catalog = snapshot["slice_catalog"]
        for lane in ("eating", "blocked"):
            for current in snapshot["plate"][lane]:
                canonical = next(
                    (item for item in catalog if _record_matches(item, current.get("slice"))), None
                )
                if canonical:
                    current.update(
                        {
                            "outcome": canonical.get("outcome"),
                            "success": canonical.get("success"),
                            "not_included": canonical.get("not_included"),
                            "canonical_state": canonical.get("canonical_state"),
                            "disposition": "current",
                        }
                    )

        for lane in ("eating", "blocked"):
            for current in snapshot["plate"][lane]:
                parents = [cake for cake in on_stand if _record_matches(cake, current.get("cake"))]
                if len(parents) == 1:
                    parents[0]["current_slices"].append(current.get("slice") or current.get("url"))
        for cake in on_stand:
            cake["condition"] = (
                "being_eaten" if cake["current_slices"] else "waiting_on_the_stand"
            )

        capacity_sources = self.config.get("portfolio", {}).get("capacity_sources", [])
        for source in capacity_sources:
            if not isinstance(source, dict):
                snapshot["source_health"].append(
                    {"source": source, "status": "unsupported", "relevance": "capacity"}
                )
                continue
            if source.get("adapter") != "trello":
                snapshot["source_health"].append(
                    {"source": source, "status": "unsupported", "relevance": "capacity"}
                )
                continue
            if not isinstance(source.get("board"), str) or not source["board"].strip():
                snapshot["source_health"].append(
                    {
                        "source": source,
                        "status": "unavailable",
                        "relevance": "capacity",
                        "error": "capacity source needs a Trello board",
                    }
                )
                continue
            try:
                board = self.trello.board(source["board"])
                cards = self.trello.cards(board)
                configured_lists = source.get("lists", [])
                if configured_lists:
                    lists = [self.trello.list(board, item) for item in configured_lists]
                    allowed = {item["id"] for item in lists}
                    cards = [card for card in cards if card.get("idList") in allowed]
                snapshot["capacity_constraints"].extend(_compact_card(card) for card in cards)
            except CakeError as exc:
                snapshot["source_health"].append(
                    {"source": source, "status": "unavailable", "relevance": "capacity", "error": str(exc)}
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
        }
        snapshot["issues"] = validate_snapshot(snapshot)
        return snapshot

    def preview(
        self,
        operations: list[dict[str, Any]],
        *,
        capacity_policies: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return preview_transition(self.snapshot(), operations, capacity_policies)

    def apply(
        self,
        operations: list[dict[str, Any]],
        confirmation_token: str,
        *,
        capacity_policies: list[dict[str, Any]] | None = None,
        allow_capacity_overage: bool = False,
    ) -> dict[str, Any]:
        preview = self.preview(operations, capacity_policies=capacity_policies)
        if preview["confirmation_token"] != confirmation_token:
            raise CakeError("The confirmation token is invalid or relevant source state changed")
        if preview["capacity_warnings"] and not allow_capacity_overage:
            raise CakeError(
                "This transition exceeds provider-owned capacity; explicitly allow the reviewed overage"
            )
        applied: list[dict[str, Any]] = []
        try:
            for operation in operations:
                self._execute(operation)
                applied.append(operation)
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
            "slice_source": cake.get("slice_source"),
            "next_slice": cake.get("next_slice"),
            **changes,
        }
        description = format_cake_contract(
            values["direction"],
            values["slice_source"],
            values.get("next_slice"),
            values.get("finished_when"),
        )
        self.trello.update_card(cake["id"], description=description)

    def _execute(self, operation: dict[str, Any]) -> None:
        action = operation["action"]
        snapshot = self.snapshot()
        if action == "nominate":
            cake = self._cake_record(snapshot, operation["cake"])
            candidate = self._candidate_record(snapshot, operation["slice"])
            self._update_cake(cake, next_slice=candidate["url"])
            return

        if action == "pull":
            cake = self._cake_record(snapshot, operation["cake"])
            candidate = self._candidate_record(snapshot, cake["next_slice"])
            _, plate_lists = self._trello_role("plate")
            target_list = plate_lists[normalize(operation.get("lane", "eating")).replace(" ", "_")]
            if candidate.get("adapter") == "plate":
                description = format_slice_contract(
                    cake["url"],
                    candidate["outcome"],
                    candidate["success"],
                    candidate.get("not_included"),
                    "current",
                )
                self.trello.update_card(
                    candidate["id"], description=description, list_id=target_list["id"], closed=False
                )
            else:
                description = f"Cake: {cake['url']}\nSlice: {candidate['url']}"
                self.trello.create_card(
                    target_list["id"],
                    name=f"{cake['name']}: {candidate['name']}",
                    description=description,
                )
            self._update_cake(cake, next_slice=None)
            return

        if action == "exit":
            current = self._current_record(snapshot, operation["plate_slice"])
            parent = self._cake_record(snapshot, current["cake"])
            disposition = normalize(operation["disposition"])
            reason = operation.get("reason")
            candidate = self._candidate_record(snapshot, current.get("slice") or current["url"])
            if candidate.get("adapter") == "github":
                body = format_slice_contract(
                    parent["url"],
                    candidate["outcome"],
                    candidate["success"],
                    candidate.get("not_included"),
                    disposition,
                    reason,
                )
                self.github.update_issue(
                    candidate["url"], title=candidate["name"], body=body
                )
                if disposition == "finished":
                    self.github.close_issue(candidate["url"])
                elif disposition == "abandoned":
                    self.github.close_issue(candidate["url"], reason=reason)
                plate_card = self.trello.card(current["plate_card"])
                proxy_desc = f"Cake: {parent['url']}\nSlice: {candidate['url']}\nDisposition: {disposition.title()}"
                if reason:
                    proxy_desc += f"\nReason: {reason}"
                self.trello.update_card(plate_card["id"], description=proxy_desc, closed=True)
            else:
                description = format_slice_contract(
                    parent["url"],
                    candidate["outcome"],
                    candidate["success"],
                    candidate.get("not_included"),
                    disposition,
                    reason,
                )
                self.trello.update_card(candidate["id"], description=description, closed=True)

            if operation.get("next_slice"):
                self._update_cake(parent, next_slice=operation["next_slice"])
            elif operation.get("cake_state"):
                self._move_cake_card(parent, operation["cake_state"], operation)
            return

        if action == "move_cake":
            cake = self._cake_record(snapshot, operation["cake"])
            self._move_cake_card(cake, operation["to"], operation)
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
            target_id = matches[0].get("plate_card") or matches[0]["id"]
            self.trello.update_card(target_id, position=target_position)
            return

        raise CakeError(f"Unknown transition action {action!r}")

    def _move_cake_card(
        self, cake: dict[str, Any], target: str, operation: dict[str, Any]
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
            "slice_source": operation.get("slice_source", cake.get("slice_source")),
            "next_slice": operation.get("next_slice", cake.get("next_slice")),
        }
        if target in {"parked", "finished"}:
            values["next_slice"] = None
        changes["description"] = format_cake_contract(
            values["direction"],
            values["slice_source"],
            values.get("next_slice"),
            values.get("finished_when"),
        )
        changes["board_id"] = stand_board["id"]
        changes["list_id"] = stand_lists[target]["id"]
        self.trello.update_card(cake["id"], **changes)


def _reference_field(description: str, field: str) -> str | None:
    prefix = f"{field}:"
    for line in description.splitlines():
        if normalize(line.split(":", 1)[0]) == normalize(field) and ":" in line:
            return line.split(":", 1)[1].strip() or None
    return None


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))
