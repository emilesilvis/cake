from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import Mock

from cake_core.doctor import CakeDoctor
from cake_core.domain import validate_snapshot


def healthy_snapshot() -> dict:
    cake_url = "https://trello.com/c/cake"
    slice_url = "https://trello.com/c/slice"
    parent = {
        "id": "cake",
        "url": cake_url,
        "name": "Useful Cake",
        "state": "on_stand",
        "direction": "Create a useful change",
        "finished_when": None,
        "repository": None,
        "slice_index": [slice_url],
        "current_slice_links": [slice_url],
        "next_slice": None,
        "available_slices": [],
    }
    candidate = {
        "id": "slice",
        "url": slice_url,
        "name": "Useful Cake: One result",
        "cake": cake_url,
        "outcome": "One result exists",
        "success": "The result is observable",
        "not_included": None,
        "plate": None,
        "github_issue": None,
        "disposition": "current",
        "adapter": "plate",
        "canonical_state": "open",
    }
    current = {
        **deepcopy(candidate),
        "plate_card": slice_url,
        "slice": slice_url,
        "lane": "eating",
    }
    snapshot = {
        "pantry": [],
        "cake_stand": {"on_stand": [parent], "parked": [], "finished": []},
        "archived_cakes": [],
        "plate": {"eating": [current], "blocked": []},
        "slice_catalog": [candidate],
        "capacity_constraints": [
            {
                "id": "gym",
                "url": "https://trello.com/c/gym",
                "name": "Gym",
                "desc": (
                    "**Cadence:** Twice weekly\n\n"
                    "**Load:** Two sessions\n\n"
                    "**Supports:** Health"
                ),
            }
        ],
        "source_health": [],
        "sources": {
            "cake_stand": {"lists": {"on_stand": {"name": "On the stand /2"}}},
            "plate": {
                "lists": {
                    "eating": {"name": "Eating /2"},
                    "blocked": {"name": "Blocked"},
                }
            },
        },
    }
    snapshot["issues"] = validate_snapshot(snapshot)
    return snapshot


class DoctorTest(unittest.TestCase):
    def test_healthy_report_stays_read_only_and_separates_priority_judgment(
        self,
    ) -> None:
        portfolio = Mock()
        portfolio.snapshot.return_value = healthy_snapshot()

        result = CakeDoctor(portfolio).check()

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["summary"]["current_slices"], 1)
        self.assertTrue(result["portfolio_challenge"]["recommended"])
        self.assertFalse(result["portfolio_challenge"]["required"])
        portfolio.github.issue.assert_not_called()

    def test_current_slice_with_parent_off_stand_routes_to_prioritise(self) -> None:
        snapshot = healthy_snapshot()
        parent = snapshot["cake_stand"]["on_stand"].pop()
        parent["state"] = "parked"
        parent["current_slice_links"] = []
        snapshot["cake_stand"]["parked"].append(parent)
        snapshot["issues"] = validate_snapshot(snapshot)
        portfolio = Mock()
        portfolio.snapshot.return_value = snapshot

        result = CakeDoctor(portfolio).check()

        finding = next(
            item for item in result["findings"] if item["code"] == "parent_not_on_stand"
        )
        self.assertIn("Useful Cake", finding["message"])
        self.assertEqual(finding["handoff"], "cake-prioritise")
        self.assertTrue(result["portfolio_challenge"]["required"])

    def test_eating_limit_counts_blocked_slices(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["plate"]["blocked"] = [deepcopy(snapshot["plate"]["eating"][0])]
        snapshot["plate"]["blocked"][0]["id"] = "blocked-copy"
        snapshot["plate"]["blocked"][0]["lane"] = "blocked"
        snapshot["sources"]["plate"]["lists"]["eating"]["name"] = "Eating /1"
        snapshot["issues"] = {"errors": [], "warnings": []}
        portfolio = Mock()
        portfolio.snapshot.return_value = snapshot

        result = CakeDoctor(portfolio).check()

        plate_wip = next(item for item in result["wip"] if item["scope"] == "plate")
        self.assertEqual(plate_wip["count"], 2)
        self.assertEqual(plate_wip["status"], "over")
        self.assertIn("cake-prioritise", result["handoffs"])

    def test_github_slice_must_link_back_to_its_plate_projection(self) -> None:
        snapshot = healthy_snapshot()
        issue_url = "https://github.com/example/cake/issues/7"
        projection_url = "https://trello.com/c/slice"
        parent = snapshot["cake_stand"]["on_stand"][0]
        parent["repository"] = "https://github.com/example/cake"
        parent["slice_index"] = [issue_url]
        canonical = snapshot["slice_catalog"][0]
        canonical.update(
            {
                "id": "example/cake#7",
                "url": issue_url,
                "adapter": "github",
                "plate": None,
            }
        )
        current = snapshot["plate"]["eating"][0]
        current.update(
            {
                **canonical,
                "id": "slice",
                "url": projection_url,
                "slice": issue_url,
                "plate_card": projection_url,
                "lane": "eating",
                "disposition": "current",
            }
        )
        snapshot["issues"] = validate_snapshot(snapshot)
        portfolio = Mock()
        portfolio.snapshot.return_value = snapshot

        result = CakeDoctor(portfolio).check()

        finding = next(
            item
            for item in result["findings"]
            if item["code"] == "plate_projection_link_drift"
        )
        self.assertEqual(finding["handoff"], "cake-prioritise")

    def test_missing_available_slice_is_reported_in_human_terms(self) -> None:
        snapshot = healthy_snapshot()
        parent = snapshot["cake_stand"]["on_stand"][0]
        candidate = deepcopy(snapshot["slice_catalog"][0])
        candidate.update(
            {
                "id": "later",
                "url": "https://trello.com/c/later",
                "name": "Useful Cake: Later result",
                "disposition": "candidate",
                "canonical_state": "archived",
            }
        )
        snapshot["slice_catalog"].append(candidate)
        parent["available_slices"] = []
        snapshot["issues"] = validate_snapshot(snapshot)
        portfolio = Mock()
        portfolio.snapshot.return_value = snapshot

        result = CakeDoctor(portfolio).check()

        finding = next(
            item
            for item in result["findings"]
            if item["code"] == "available_slices_drift"
        )
        self.assertIn("other Slices available to eat", finding["message"])
        self.assertEqual(finding["handoff"], "cake-slice")


if __name__ == "__main__":
    unittest.main()
