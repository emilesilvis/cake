from __future__ import annotations

from copy import deepcopy
import unittest

from cake_core.domain import (
    CakeError,
    format_cake_contract,
    format_plate_projection_contract,
    format_slice_contract,
    github_repository_name,
    is_github_issue_url,
    is_trello_card_url,
    parse_cake_contract,
    parse_plate_projection_contract,
    parse_slice_contract,
    preview_transition,
    canonical_ref,
    trello_card_url,
    validate_snapshot,
)


def cake(
    reference: str,
    *,
    next_slice: str | None = None,
    repository: str | None = None,
) -> dict:
    return {
        "id": reference,
        "url": f"https://trello.com/c/{reference}",
        "name": reference,
        "state": "on_stand",
        "direction": "Make useful progress",
        "finished_when": None,
        "repository": repository,
        "slice_index": [],
        "current_slice_links": [],
        "previous_slice": None,
        "next_slice": next_slice,
        "available_slices": [],
    }


def slice_record(reference: str, parent: dict, disposition: str = "candidate") -> dict:
    return {
        "id": reference,
        "url": f"https://trello.com/c/{reference}",
        "name": reference,
        "cake": parent["url"],
        "outcome": "One result exists",
        "success": "The result is observable",
        "not_included": None,
        "github_issue": None,
        "disposition": disposition,
        "adapter": "plate",
        "canonical_state": "archived",
    }


def snapshot(cakes: list[dict], slices: list[dict], eating: list[dict] | None = None) -> dict:
    current_slices = eating or []
    current_keys = {
        canonical_ref(item.get("slice") or item.get("url")) for item in current_slices
    }
    for parent in cakes:
        parent["slice_index"] = [
            item["url"]
            for item in slices
            if canonical_ref(item["cake"]) == canonical_ref(parent["url"])
            and item["adapter"] == ("github" if parent.get("repository") else "plate")
        ]
        parent["current_slice_links"] = [
            item["plate_card"]
            for item in current_slices
            if canonical_ref(item["cake"]) == canonical_ref(parent["url"])
        ]
        parent["available_slices"] = [
            item["url"]
            for item in slices
            if canonical_ref(item["cake"]) == canonical_ref(parent["url"])
            and item["adapter"] == ("github" if parent.get("repository") else "plate")
            and item.get("disposition") in {"candidate", "paused"}
            and canonical_ref(item["url"]) not in current_keys
            and canonical_ref(item["url"]) != canonical_ref(parent.get("next_slice"))
        ]
    return {
        "pantry": [],
        "cake_stand": {"on_stand": cakes, "parked": [], "finished": []},
        "plate": {"eating": current_slices, "blocked": []},
        "slice_catalog": slices,
        "source_health": [],
    }


def current(record: dict, parent: dict, lane: str = "eating") -> dict:
    return {
        **deepcopy(record),
        "id": record["id"],
        "plate_card": record["url"],
        "slice": record["url"],
        "cake": parent["url"],
        "lane": lane,
        "disposition": "current",
        "canonical_state": "open",
    }


class ContractTest(unittest.TestCase):
    def test_contracts_round_trip(self) -> None:
        cake_body = format_cake_contract(
            "Publish consistently", "https://trello.com/c/slice", "Habit is stable"
        )
        self.assertEqual(
            parse_cake_contract(cake_body),
            {
                "direction": "Publish consistently",
                "finished_when": "Habit is stable",
                "repository": None,
                "slice_index": [],
                "current_slice_links": [],
                "previous_slice": None,
                "next_slice": "https://trello.com/c/slice",
                "available_slices": [],
            },
        )
        slice_body = format_slice_contract(
            "https://trello.com/c/cake",
            "Discovery feed is usable",
            "A reader can discover posts",
            "Ranking",
        )
        self.assertEqual(parse_slice_contract(slice_body)["not_included"], "Ranking")

    def test_trello_markdown_contracts_render_cleanly_and_round_trip(self) -> None:
        body = format_slice_contract(
            "https://trello.com/c/cake",
            "Discovery feed is usable",
            "A reader can discover posts",
            "Ranking",
            disposition="current",
            trello_markdown=True,
        )

        self.assertEqual(
            body,
            "**Cake:** https://trello.com/c/cake\n\n"
            "**Outcome:** Discovery feed is usable\n\n"
            "**Success:** A reader can discover posts\n\n"
            "**Not included:** Ranking\n\n"
            "**Disposition:** Current",
        )
        self.assertEqual(
            parse_slice_contract(body),
            {
                "cake": "https://trello.com/c/cake",
                "outcome": "Discovery feed is usable",
                "success": "A reader can discover posts",
                "not_included": "Ranking",
                "plate": None,
                "github_issue": None,
                "disposition": "current",
                "reason": None,
            },
        )

    def test_trello_markdown_cake_and_projection_contracts_round_trip(self) -> None:
        cake_body = format_cake_contract(
            "Publish consistently",
            next_slice="https://trello.com/c/slice",
            trello_markdown=True,
        )
        projection_body = format_plate_projection_contract(
            "https://github.com/example/blog/issues/7",
            "https://trello.com/c/cake",
            trello_markdown=True,
        )

        self.assertIn("**Direction:** Publish consistently", cake_body)
        self.assertIn("\n\n**Next slice:** https://trello.com/c/slice", cake_body)
        self.assertEqual(
            parse_cake_contract(cake_body)["next_slice"],
            "https://trello.com/c/slice",
        )
        self.assertEqual(
            parse_plate_projection_contract(projection_body),
            {
                "slice": "https://github.com/example/blog/issues/7",
                "cake": "https://trello.com/c/cake",
                "disposition": "current",
            },
        )

    def test_current_slice_links_round_trip_as_stable_urls(self) -> None:
        body = format_cake_contract(
            "Publish consistently",
            current_slices=(
                "https://trello.com/c/alpha/a-long-title",
                "https://www.trello.com/c/beta?filter=open",
            ),
        )
        self.assertEqual(
            parse_cake_contract(body)["current_slice_links"],
            ["https://trello.com/c/alpha", "https://trello.com/c/beta"],
        )

    def test_parked_previous_slice_round_trips_as_historical_navigation(self) -> None:
        body = format_cake_contract(
            "Publish consistently",
            previous_slice="https://trello.com/c/previous/a-long-title",
        )

        self.assertEqual(
            parse_cake_contract(body)["previous_slice"],
            "https://trello.com/c/previous",
        )
        self.assertIn("Previous slice: https://trello.com/c/previous", body)

    def test_previous_slice_cannot_coexist_with_current_or_next_navigation(self) -> None:
        with self.assertRaisesRegex(CakeError, "Previous Slice"):
            format_cake_contract(
                "Publish consistently",
                next_slice="https://trello.com/c/next",
                previous_slice="https://trello.com/c/previous",
            )

    def test_repository_attachment_keeps_terminal_trello_history_valid(self) -> None:
        parent = cake("cake", repository="https://github.com/example/cake")
        parent["state"] = "parked"
        finished = slice_record("previous", parent, disposition="finished")
        parent["previous_slice"] = finished["url"]
        source = {
            "pantry": [],
            "cake_stand": {
                "on_stand": [],
                "parked": [parent],
                "finished": [],
            },
            "plate": {"eating": [], "blocked": []},
            "slice_catalog": [finished],
            "source_health": [],
        }

        self.assertEqual(validate_snapshot(source), {"errors": [], "warnings": []})

    def test_trello_full_and_short_urls_are_the_same_reference(self) -> None:
        self.assertEqual(
            canonical_ref("https://trello.com/c/AbC123xy/a-card-title"),
            canonical_ref("https://trello.com/c/AbC123xy"),
        )
        self.assertEqual(
            trello_card_url("https://trello.com/c/AbC123xy/a-card-title"),
            "https://trello.com/c/AbC123xy",
        )
        self.assertTrue(is_trello_card_url("https://trello.com/c/AbC123xy"))

    def test_repository_and_available_slices_round_trip(self) -> None:
        issue = "https://github.com/example/blog/issues/7"
        other = "https://github.com/example/blog/issues/8"
        body = format_cake_contract(
            "Publish consistently",
            next_slice=issue,
            repository="example/blog",
            available_slices=[other],
        )
        parsed = parse_cake_contract(body)
        self.assertEqual(parsed["repository"], "https://github.com/example/blog")
        self.assertEqual(parsed["available_slices"], [other])
        self.assertEqual(parsed["next_slice"], issue)
        self.assertNotIn("Slice index:", body)
        self.assertEqual(github_repository_name(parsed["repository"]), "example/blog")
        self.assertTrue(is_github_issue_url(issue))

    def test_github_slice_plate_backlink_round_trips(self) -> None:
        plate = "https://trello.com/c/projection"
        body = format_slice_contract(
            "https://trello.com/c/cake",
            "Outcome",
            "Success",
            disposition="current",
            plate=plate,
        )
        self.assertEqual(parse_slice_contract(body)["plate"], plate)

    def test_plate_projection_contract_round_trips(self) -> None:
        issue = "https://github.com/example/blog/issues/7"
        body = format_plate_projection_contract(issue, "https://trello.com/c/cake")
        self.assertEqual(
            parse_plate_projection_contract(body),
            {"slice": issue, "cake": "https://trello.com/c/cake", "disposition": "current"},
        )

    def test_plate_backlink_must_be_a_trello_card_url(self) -> None:
        with self.assertRaisesRegex(CakeError, "Plate projection"):
            format_slice_contract(
                "https://trello.com/c/cake",
                "Outcome",
                "Success",
                plate="not-a-trello-card",
            )

    def test_abandon_requires_a_reason(self) -> None:
        with self.assertRaisesRegex(CakeError, "needs a reason"):
            format_slice_contract(
                "https://trello.com/c/cake",
                "Outcome",
                "Success",
                disposition="abandoned",
            )

    def test_slice_parent_must_be_a_clickable_trello_link(self) -> None:
        with self.assertRaisesRegex(CakeError, "Trello card URL"):
            format_slice_contract("a-card-id", "Outcome", "Success")


class TransitionTest(unittest.TestCase):
    def test_archiving_a_parked_cake_keeps_it_as_a_historical_slice_parent(self) -> None:
        parent = cake("old-routine")
        parent["state"] = "parked"
        old_slice = slice_record("old-occurrence", parent, disposition="abandoned")
        source = snapshot([], [old_slice])
        source["cake_stand"]["parked"] = [parent]

        result = preview_transition(
            source,
            [{"action": "archive_cake", "cake": parent["url"]}],
        )

        self.assertEqual(result["target"]["cake_stand"]["parked"], [])
        self.assertEqual(result["target"]["archived_cakes"][0]["state"], "archived")
        self.assertEqual(result["target_issues"]["errors"], [])

    def test_only_a_parked_cake_can_be_archived(self) -> None:
        parent = cake("active")
        with self.assertRaisesRegex(CakeError, "No Parked Cake"):
            preview_transition(
                snapshot([parent], []),
                [{"action": "archive_cake", "cake": parent["url"]}],
            )

    def test_pull_uses_only_next_slice_and_clears_pointer(self) -> None:
        parent = cake("blog", next_slice="https://trello.com/c/feed")
        candidate = slice_record("feed", parent)
        result = preview_transition(
            snapshot([parent], [candidate]),
            [{"action": "pull", "cake": parent["url"], "lane": "eating"}],
        )
        target_parent = result["target"]["cake_stand"]["on_stand"][0]
        self.assertIsNone(target_parent["next_slice"])
        self.assertEqual(target_parent["current_slice_links"], [candidate["url"]])
        self.assertEqual(target_parent["available_slices"], [])
        self.assertEqual(result["target"]["plate"]["eating"][0]["slice"], candidate["url"])

    def test_nominating_a_slice_swaps_it_with_the_previous_next_slice(self) -> None:
        old_next = "https://trello.com/c/old"
        parent = cake("blog", next_slice=old_next)
        old = slice_record("old", parent)
        chosen = slice_record("chosen", parent)

        result = preview_transition(
            snapshot([parent], [old, chosen]),
            [{"action": "nominate", "cake": parent["url"], "slice": chosen["url"]}],
        )

        target = result["target"]["cake_stand"]["on_stand"][0]
        self.assertEqual(target["next_slice"], chosen["url"])
        self.assertEqual(target["available_slices"], [old["url"]])

    def test_pull_of_github_slice_plans_a_plate_projection(self) -> None:
        issue_url = "https://github.com/example/blog/issues/7"
        parent = cake("blog", next_slice=issue_url, repository="example/blog")
        candidate = {
            "id": "example/blog#7",
            "url": issue_url,
            "name": "Blog: Rewrite five posts",
            "cake": parent["url"],
            "outcome": "Five posts read naturally",
            "success": "All five pass the checker",
            "not_included": None,
            "plate": None,
            "disposition": "candidate",
            "adapter": "github",
            "canonical_state": "open",
        }

        result = preview_transition(
            snapshot([parent], [candidate]),
            [{"action": "pull", "cake": parent["url"], "lane": "eating"}],
        )

        target_parent = result["target"]["cake_stand"]["on_stand"][0]
        current_slice = result["target"]["plate"]["eating"][0]
        self.assertEqual(current_slice["slice"], issue_url)
        self.assertTrue(current_slice["plate_card"].startswith("planned:plate-projection:"))
        self.assertEqual(target_parent["current_slice_links"], [current_slice["plate_card"]])
        self.assertEqual(result["target"]["slice_catalog"][0]["plate"], current_slice["plate_card"])

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
        target_parent = result["target"]["cake_stand"]["on_stand"][0]
        self.assertIsNone(target_parent["next_slice"])
        self.assertEqual(
            target_parent["current_slice_links"], [first["url"], second["url"]]
        )

    def test_cannot_pull_an_unnominated_slice(self) -> None:
        parent = cake("piano", next_slice="https://trello.com/c/scales")
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
        self.assertEqual(
            result["target"]["cake_stand"]["on_stand"][0]["available_slices"], []
        )

    def test_paused_slice_becomes_available_while_another_slice_remains_current(self) -> None:
        parent = cake("math")
        first = slice_record("first", parent)
        second = slice_record("second", parent)
        source = snapshot(
            [parent],
            [first, second],
            [current(first, parent), current(second, parent)],
        )

        result = preview_transition(
            source,
            [{"action": "exit", "plate_slice": first["url"], "disposition": "paused"}],
        )

        target = result["target"]["cake_stand"]["on_stand"][0]
        self.assertEqual(target["available_slices"], [first["url"]])

    def test_parking_after_the_last_exit_shows_that_slice_as_previous(self) -> None:
        parent = cake("wolf-tone")
        extracted = slice_record("extract-zachlab", parent)
        source = snapshot([parent], [extracted], [current(extracted, parent)])

        result = preview_transition(
            source,
            [
                {
                    "action": "exit",
                    "plate_slice": extracted["url"],
                    "disposition": "finished",
                    "cake_state": "parked",
                }
            ],
        )

        target = result["target"]["cake_stand"]["parked"][0]
        self.assertEqual(target["previous_slice"], extracted["url"])
        self.assertEqual(target["available_slices"], [])
        self.assertEqual(result["target_issues"]["errors"], [])

    def test_paused_previous_slice_remains_available_when_its_cake_is_parked(self) -> None:
        parent = cake("wolf-tone")
        extracted = slice_record("extract-zachlab", parent)
        source = snapshot([parent], [extracted], [current(extracted, parent)])

        result = preview_transition(
            source,
            [
                {
                    "action": "exit",
                    "plate_slice": extracted["url"],
                    "disposition": "paused",
                    "cake_state": "parked",
                }
            ],
        )

        target = result["target"]["cake_stand"]["parked"][0]
        self.assertEqual(target["previous_slice"], extracted["url"])
        self.assertEqual(target["available_slices"], [extracted["url"]])

    def test_cake_cannot_leave_stand_while_a_slice_is_current(self) -> None:
        parent = cake("blog")
        feed = slice_record("feed", parent)
        source = snapshot([parent], [feed], [current(feed, parent)])
        with self.assertRaisesRegex(CakeError, "Resolve every current Slice"):
            preview_transition(
                source,
                [{"action": "move_cake", "cake": parent["url"], "to": "parked"}],
            )

    def test_parking_a_waiting_cake_recovers_its_previous_slice_from_history(self) -> None:
        parent = cake("blog", next_slice="https://trello.com/c/next")
        previous = slice_record("previous", parent, disposition="finished")
        upcoming = slice_record("next", parent)
        source = snapshot([parent], [previous, upcoming])

        result = preview_transition(
            source,
            [{"action": "move_cake", "cake": parent["url"], "to": "parked"}],
        )

        target = result["target"]["cake_stand"]["parked"][0]
        self.assertEqual(target["previous_slice"], previous["url"])
        self.assertIsNone(target["next_slice"])
        self.assertEqual(target["available_slices"], [upcoming["url"]])

    def test_promoting_a_pantry_cake_adopts_its_current_slice_link(self) -> None:
        parent = cake("orb")
        parent["state"] = "pantry"
        grill = slice_record("grill", parent)
        plate_slice = current(grill, parent)
        source = snapshot([], [grill], [plate_slice])
        source["pantry"] = [parent]

        result = preview_transition(
            source,
            [{"action": "move_cake", "cake": parent["url"], "to": "on_stand"}],
        )

        promoted = result["target"]["cake_stand"]["on_stand"][0]
        self.assertEqual(promoted["current_slice_links"], [grill["url"]])
        self.assertIsNone(promoted["next_slice"])
        self.assertEqual(result["target_issues"]["errors"], [])

    def test_blocked_slice_counts_toward_soft_plate_limit(self) -> None:
        first_parent = cake("one", next_slice="https://trello.com/c/one-slice")
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
        valid = cake("valid", next_slice="https://trello.com/c/valid-slice")
        broken = cake("broken")
        candidate = slice_record("valid-slice", valid)
        result = preview_transition(
            snapshot([valid, broken], [candidate]),
            [{"action": "pull", "cake": valid["url"]}],
        )
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["source_issues"]["errors"][0]["code"], "waiting_without_next_slice")

    def test_relevant_unavailable_source_fails_closed(self) -> None:
        parent = cake("blog", next_slice="https://trello.com/c/feed")
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
        parent = cake("blog", next_slice="https://trello.com/c/feed")
        candidate = slice_record("feed", parent)
        source = snapshot([parent], [candidate])
        source["source_health"] = [
            {
                "source": "https://trello.com/c/unknown",
                "status": "unavailable",
                "relevance": "plate_membership",
                "error": "visible card is in an unconfigured list",
            }
        ]
        with self.assertRaisesRegex(CakeError, "required by this transition"):
            preview_transition(source, [{"action": "pull", "cake": parent["url"]}])

    def test_confirmation_token_tracks_affected_not_unrelated_state(self) -> None:
        parent = cake("blog", next_slice="https://trello.com/c/feed")
        candidate = slice_record("feed", parent)
        source = snapshot([parent], [candidate])
        source["priority"] = "Publish useful work"
        source["pantry"] = [{"id": "maybe", "url": "https://trello.com/c/maybe", "name": "Maybe"}]
        source["capacity"] = {
            "rhythms": [
                {
                    "id": "gym",
                    "progress": {"remaining": {"occurrences": 2, "unit": "session"}},
                }
            ]
        }
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

        rhythm_change = deepcopy(source)
        rhythm_change["capacity"]["rhythms"][0]["progress"]["remaining"][
            "occurrences"
        ] = 1
        self.assertNotEqual(
            preview_transition(rhythm_change, operation)["confirmation_token"], original
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
