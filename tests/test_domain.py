from __future__ import annotations

from copy import deepcopy
import unittest

from cake_core.domain import (
    CakeError,
    format_cake_contract,
    format_slice_contract,
    parse_cake_contract,
    parse_slice_contract,
    parse_slice_source,
    preview_transition,
    validate_snapshot,
)


def cake(reference: str, *, next_slice: str | None = None) -> dict:
    return {
        "id": reference,
        "url": f"https://trello.test/c/{reference}",
        "name": reference,
        "state": "on_stand",
        "direction": "Make useful progress",
        "finished_when": None,
        "slice_source": "plate",
        "next_slice": next_slice,
    }


def slice_record(reference: str, parent: dict, disposition: str = "candidate") -> dict:
    return {
        "id": reference,
        "url": f"https://trello.test/c/{reference}",
        "name": reference,
        "cake": parent["url"],
        "outcome": "One result exists",
        "success": "The result is observable",
        "not_included": None,
        "disposition": disposition,
        "adapter": "plate",
        "canonical_state": "archived",
    }


def snapshot(cakes: list[dict], slices: list[dict], eating: list[dict] | None = None) -> dict:
    return {
        "pantry": [],
        "cake_stand": {"on_stand": cakes, "parked": [], "finished": []},
        "plate": {"eating": eating or [], "blocked": []},
        "slice_catalog": slices,
        "source_health": [],
    }


def current(record: dict, parent: dict, lane: str = "eating") -> dict:
    return {
        **deepcopy(record),
        "id": f"plate-{record['id']}",
        "plate_card": f"plate-{record['id']}",
        "slice": record["url"],
        "cake": parent["url"],
        "lane": lane,
        "disposition": "current",
        "canonical_state": "open",
    }


class ContractTest(unittest.TestCase):
    def test_contracts_round_trip(self) -> None:
        cake_body = format_cake_contract(
            "Publish consistently", "plate", "https://trello.test/c/slice", "Habit is stable"
        )
        self.assertEqual(
            parse_cake_contract(cake_body),
            {
                "direction": "Publish consistently",
                "finished_when": "Habit is stable",
                "slice_source": "plate",
                "next_slice": "https://trello.test/c/slice",
            },
        )
        slice_body = format_slice_contract(
            "cake", "Discovery feed is usable", "A reader can discover posts", "Ranking"
        )
        self.assertEqual(parse_slice_contract(slice_body)["not_included"], "Ranking")

    def test_github_source_must_define_a_collection(self) -> None:
        with self.assertRaisesRegex(CakeError, "needs a query"):
            parse_slice_source("github:owner/repository")
        self.assertEqual(
            parse_slice_source("github:owner/repository?query=label%3Acake-slice"),
            {
                "adapter": "github",
                "repository": "owner/repository",
                "query": "label:cake-slice",
            },
        )

    def test_abandon_requires_a_reason(self) -> None:
        with self.assertRaisesRegex(CakeError, "needs a reason"):
            format_slice_contract("cake", "Outcome", "Success", disposition="abandoned")


class TransitionTest(unittest.TestCase):
    def test_pull_uses_only_next_slice_and_clears_pointer(self) -> None:
        parent = cake("blog", next_slice="https://trello.test/c/feed")
        candidate = slice_record("feed", parent)
        result = preview_transition(
            snapshot([parent], [candidate]),
            [{"action": "pull", "cake": parent["url"], "lane": "eating"}],
        )
        target_parent = result["target"]["cake_stand"]["on_stand"][0]
        self.assertIsNone(target_parent["next_slice"])
        self.assertEqual(result["target"]["plate"]["eating"][0]["slice"], candidate["url"])

    def test_nominate_and_pull_can_add_a_second_current_slice(self) -> None:
        parent = cake("masters")
        first = slice_record("essay", parent)
        second = slice_record("research", parent)
        source = snapshot([parent], [first, second], [current(first, parent)])
        result = preview_transition(
            source,
            [
                {"action": "nominate", "cake": parent["url"], "slice": second["url"]},
                {"action": "pull", "cake": parent["url"], "lane": "eating"},
            ],
        )
        self.assertEqual(len(result["target"]["plate"]["eating"]), 2)
        self.assertIsNone(result["target"]["cake_stand"]["on_stand"][0]["next_slice"])

    def test_cannot_pull_an_unnominated_slice(self) -> None:
        parent = cake("piano", next_slice="https://trello.test/c/scales")
        nominated = slice_record("scales", parent)
        with self.assertRaisesRegex(CakeError, "does not accept fields: slice"):
            preview_transition(
                snapshot([parent], [nominated]),
                [{"action": "pull", "cake": parent["url"], "slice": "something-else"}],
            )

    def test_last_exit_requires_parent_resolution(self) -> None:
        parent = cake("math")
        lesson = slice_record("lesson", parent)
        source = snapshot([parent], [lesson], [current(lesson, parent)])
        with self.assertRaisesRegex(CakeError, "nominate another Slice or Park/Finish"):
            preview_transition(
                source,
                [{"action": "exit", "plate_slice": lesson["url"], "disposition": "finished"}],
            )

    def test_paused_slice_can_become_the_next_slice(self) -> None:
        parent = cake("math")
        lesson = slice_record("lesson", parent)
        source = snapshot([parent], [lesson], [current(lesson, parent)])
        result = preview_transition(
            source,
            [
                {
                    "action": "exit",
                    "plate_slice": lesson["url"],
                    "disposition": "paused",
                    "next_slice": lesson["url"],
                }
            ],
        )
        self.assertEqual(
            result["target"]["cake_stand"]["on_stand"][0]["next_slice"], lesson["url"]
        )
        self.assertEqual(result["target"]["slice_catalog"][0]["disposition"], "paused")

    def test_cake_cannot_leave_stand_while_a_slice_is_current(self) -> None:
        parent = cake("blog")
        feed = slice_record("feed", parent)
        source = snapshot([parent], [feed], [current(feed, parent)])
        with self.assertRaisesRegex(CakeError, "Resolve every current Slice"):
            preview_transition(
                source,
                [{"action": "move_cake", "cake": parent["url"], "to": "parked"}],
            )

    def test_blocked_slice_counts_toward_soft_plate_limit(self) -> None:
        first_parent = cake("one", next_slice="https://trello.test/c/one-slice")
        second_parent = cake("two")
        first = slice_record("one-slice", first_parent)
        second = slice_record("two-slice", second_parent)
        source = snapshot([first_parent, second_parent], [first, second], [current(second, second_parent)])
        source["plate"]["blocked"] = source["plate"].pop("eating")
        source["plate"]["eating"] = []
        result = preview_transition(
            source,
            [{"action": "pull", "cake": first_parent["url"]}],
            [{"scope": "plate", "label": "Plate", "limit": 1}],
        )
        warning = result["capacity_warnings"][0]
        self.assertEqual(warning["after"], 2)
        self.assertFalse(warning["blocking"])

    def test_unrelated_existing_error_does_not_block_transition(self) -> None:
        valid = cake("valid", next_slice="https://trello.test/c/valid-slice")
        broken = cake("broken")
        candidate = slice_record("valid-slice", valid)
        result = preview_transition(
            snapshot([valid, broken], [candidate]),
            [{"action": "pull", "cake": valid["url"]}],
        )
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["source_issues"]["errors"][0]["code"], "waiting_without_next_slice")

    def test_relevant_unavailable_source_fails_closed(self) -> None:
        parent = cake("blog", next_slice="https://trello.test/c/feed")
        candidate = slice_record("feed", parent)
        source = snapshot([parent], [candidate])
        source["source_health"] = [
            {
                "cake": parent["url"],
                "source": "plate",
                "status": "unavailable",
                "error": "offline",
            }
        ]
        with self.assertRaisesRegex(CakeError, "required by this transition"):
            preview_transition(source, [{"action": "pull", "cake": parent["url"]}])

    def test_unknown_visible_plate_membership_fails_closed(self) -> None:
        parent = cake("blog", next_slice="https://trello.test/c/feed")
        candidate = slice_record("feed", parent)
        source = snapshot([parent], [candidate])
        source["source_health"] = [
            {
                "source": "https://trello.test/c/unknown",
                "status": "unavailable",
                "relevance": "plate_membership",
                "error": "visible card is in an unconfigured list",
            }
        ]
        with self.assertRaisesRegex(CakeError, "required by this transition"):
            preview_transition(source, [{"action": "pull", "cake": parent["url"]}])

    def test_confirmation_token_tracks_affected_not_unrelated_state(self) -> None:
        parent = cake("blog", next_slice="https://trello.test/c/feed")
        candidate = slice_record("feed", parent)
        source = snapshot([parent], [candidate])
        source["priority"] = "Publish useful work"
        source["pantry"] = [{"id": "maybe", "url": "https://trello.test/c/maybe", "name": "Maybe"}]
        operation = [{"action": "pull", "cake": parent["url"]}]
        original = preview_transition(source, operation)["confirmation_token"]

        unrelated_change = deepcopy(source)
        unrelated_change["pantry"][0]["name"] = "Maybe later"
        self.assertEqual(
            preview_transition(unrelated_change, operation)["confirmation_token"], original
        )

        relevant_change = deepcopy(source)
        relevant_change["slice_catalog"][0]["success"] = "A different observable result"
        self.assertNotEqual(
            preview_transition(relevant_change, operation)["confirmation_token"], original
        )

    def test_closed_canonical_slice_on_plate_is_reported_as_drift(self) -> None:
        parent = cake("blog")
        feed = slice_record("feed", parent)
        plate_slice = current(feed, parent)
        plate_slice["canonical_state"] = "closed"
        issues = validate_snapshot(snapshot([parent], [feed], [plate_slice]))
        self.assertEqual(issues["warnings"][0]["code"], "terminal_slice_on_plate")


if __name__ == "__main__":
    unittest.main()
