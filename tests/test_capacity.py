from __future__ import annotations

from datetime import datetime, timezone
import unittest

from cake_core.capacity import (
    current_period,
    observe_rhythms,
    parse_rhythm_contract,
    quantify_rhythm_load,
    rhythm_checklist_plan,
    rhythm_checklist_spec,
    rhythm_progress,
)
from cake_core.domain import CakeError


NOW = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
TIMEZONE = "Europe/Amsterdam"


def constraint(identifier: str, name: str, cadence: str, load: str) -> dict:
    return {
        "id": identifier,
        "url": f"https://trello.com/c/{identifier}",
        "shortLink": identifier,
        "name": name,
        "desc": f"Cadence: {cadence}\nLoad: {load}\nSupports: A continuing benefit",
    }


def checklist(identifier: str, name: str, *items: tuple[str, str]) -> dict:
    return {
        "id": identifier,
        "name": name,
        "checkItems": [
            {
                "id": f"{identifier}-{index}",
                "name": item_name,
                "state": state,
                "pos": index,
            }
            for index, (item_name, state) in enumerate(items, start=1)
        ],
    }


class RhythmContractTest(unittest.TestCase):
    def test_contract_parses_plain_and_trello_markdown(self) -> None:
        self.assertEqual(
            parse_rhythm_contract(
                "**Cadence:** Twice weekly\n\n"
                "**Load:** Two sessions per week\n\n"
                "**Supports:** Health"
            ),
            {
                "cadence": "Twice weekly",
                "load": "Two sessions per week",
                "supports": "Health",
            },
        )

    def test_current_cards_have_quantifiable_loads(self) -> None:
        self.assertEqual(
            quantify_rhythm_load(
                "Twice weekly, normally Monday and Wednesday.",
                "Two gym sessions per week.",
            ),
            {
                "period": "week",
                "occurrences": 2,
                "unit": "session",
                "minutes_per_occurrence": None,
                "minutes": None,
            },
        )
        self.assertEqual(
            quantify_rhythm_load(
                "Sunday through Friday.",
                "One 30-minute MuseFlow session, six times per week.",
            )["minutes"],
            180,
        )
        self.assertEqual(
            quantify_rhythm_load(
                "Tuesday through Friday.",
                "Four focused one-hour study sessions per week.",
            )["minutes"],
            240,
        )
        self.assertEqual(
            quantify_rhythm_load(
                "Daily logging with a Monday–Sunday weekly average.",
                "Log intake every day and review the weekly average.",
            )["occurrences"],
            7,
        )

    def test_week_uses_local_monday_to_monday_boundaries(self) -> None:
        period = current_period(
            "week",
            now=NOW,
            timezone_name=TIMEZONE,
        )

        self.assertEqual(period["start"], "2026-08-09T22:00:00Z")
        self.assertEqual(period["end"], "2026-08-16T22:00:00Z")


class RhythmChecklistTest(unittest.TestCase):
    def test_current_period_specs_use_named_days_when_the_cadence_provides_them(self) -> None:
        gym = constraint(
            "gym",
            "Gym",
            "Twice weekly, normally Monday and Wednesday.",
            "Two gym sessions per week.",
        )
        piano = constraint(
            "piano",
            "Piano",
            "Sunday through Friday.",
            "One 30-minute MuseFlow session, six times per week.",
        )

        gym_spec = rhythm_checklist_spec(gym, now=NOW, timezone_name=TIMEZONE)
        piano_spec = rhythm_checklist_spec(piano, now=NOW, timezone_name=TIMEZONE)

        self.assertEqual(gym_spec["name"], "Cake · 2026-08-10–2026-08-16")
        self.assertEqual(gym_spec["items"], ["Monday", "Wednesday"])
        self.assertEqual(
            piano_spec["items"],
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"],
        )

    def test_checkmarks_report_completed_and_remaining_load(self) -> None:
        cards = [
            constraint(
                "gym",
                "Gym",
                "Twice weekly, normally Monday and Wednesday.",
                "Two gym sessions per week.",
            ),
            constraint(
                "maths",
                "Maths",
                "Tuesday through Friday.",
                "Four focused one-hour study sessions per week.",
            ),
            constraint(
                "piano",
                "Piano",
                "Sunday through Friday.",
                "One 30-minute MuseFlow session, six times per week.",
            ),
        ]
        current_name = "Cake · 2026-08-10–2026-08-16"
        checklists = {
            "gym": [
                checklist(
                    "gym-list",
                    current_name,
                    ("Monday", "complete"),
                    ("Wednesday", "incomplete"),
                )
            ],
            "maths": [
                checklist(
                    "maths-list",
                    current_name,
                    ("Tuesday", "complete"),
                    ("Wednesday", "complete"),
                    ("Thursday", "incomplete"),
                    ("Friday", "incomplete"),
                )
            ],
            "piano": [
                checklist(
                    "piano-list",
                    current_name,
                    ("Monday", "complete"),
                    ("Tuesday", "complete"),
                    ("Wednesday", "incomplete"),
                    ("Thursday", "incomplete"),
                    ("Friday", "incomplete"),
                    ("Sunday", "incomplete"),
                )
            ],
        }

        observed = observe_rhythms(
            cards,
            checklists,
            now=NOW,
            timezone_name=TIMEZONE,
        )
        by_name = {item["name"]: item["progress"] for item in observed}

        self.assertEqual(by_name["Gym"]["completed"]["occurrences"], 1)
        self.assertEqual(by_name["Gym"]["remaining"]["occurrences"], 1)
        self.assertEqual(by_name["Maths"]["completed"]["occurrences"], 2)
        self.assertEqual(by_name["Maths"]["remaining"]["minutes"], 120)
        self.assertEqual(by_name["Piano"]["completed"]["occurrences"], 2)
        self.assertEqual(by_name["Piano"]["remaining"]["minutes"], 120)

    def test_missing_current_checklist_needs_sync(self) -> None:
        card = constraint("gym", "Gym", "Twice weekly.", "Two sessions per week.")

        progress = rhythm_progress(card, [], now=NOW, timezone_name=TIMEZONE)

        self.assertEqual(progress["status"], "needs_sync")
        self.assertEqual(progress["remaining"]["occurrences"], 2)

    def test_plan_creates_a_current_checklist_when_none_is_managed(self) -> None:
        card = constraint("gym", "Gym", "Twice weekly.", "Two sessions per week.")

        plan = rhythm_checklist_plan(card, [], now=NOW, timezone_name=TIMEZONE)

        self.assertEqual(plan["status"], "needs_sync")
        self.assertEqual(
            plan["changes"],
            [
                {
                    "action": "create_checklist",
                    "card": "gym",
                    "name": "Cake · 2026-08-10–2026-08-16",
                    "items": ["Occurrence 1", "Occurrence 2"],
                }
            ],
        )

    def test_rollover_renames_reconciles_and_resets_the_managed_checklist(self) -> None:
        card = constraint("gym", "Gym", "Twice weekly.", "Two sessions per week.")
        old = checklist(
            "managed",
            "Cake · 2026-08-03–2026-08-09",
            ("Old first", "complete"),
            ("Old second", "incomplete"),
            ("Old extra", "complete"),
        )

        plan = rhythm_checklist_plan(card, [old], now=NOW, timezone_name=TIMEZONE)

        self.assertEqual(
            [change["action"] for change in plan["changes"]],
            [
                "rename_checklist",
                "update_check_item",
                "update_check_item",
                "delete_check_item",
            ],
        )
        self.assertEqual(plan["changes"][1]["to"]["state"], "incomplete")
        self.assertEqual(plan["changes"][2]["to"]["state"], "incomplete")

    def test_current_period_never_resets_checked_items(self) -> None:
        card = constraint("gym", "Gym", "Twice weekly.", "Two sessions per week.")
        current = checklist(
            "managed",
            "Cake · 2026-08-10–2026-08-16",
            ("Occurrence 1", "complete"),
            ("Occurrence 2", "incomplete"),
        )

        plan = rhythm_checklist_plan(card, [current], now=NOW, timezone_name=TIMEZONE)

        self.assertEqual(plan["status"], "current")
        self.assertEqual(plan["changes"], [])

    def test_more_than_one_managed_checklist_is_ambiguous(self) -> None:
        card = constraint("gym", "Gym", "Twice weekly.", "Two sessions per week.")

        with self.assertRaisesRegex(CakeError, "more than one Cake-managed"):
            rhythm_checklist_plan(
                card,
                [
                    checklist("one", "Cake · 2026-08-03–2026-08-09"),
                    checklist("two", "Cake · 2026-08-10–2026-08-16"),
                ],
                now=NOW,
                timezone_name=TIMEZONE,
            )


if __name__ == "__main__":
    unittest.main()
