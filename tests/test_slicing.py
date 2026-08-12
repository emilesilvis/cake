from __future__ import annotations

import unittest
from unittest.mock import Mock

from cake_core.domain import CakeError, format_slice_contract
from cake_core.slicing import CakeSlicer


def parent():
    return {
        "id": "cake",
        "url": "https://trello.com/c/cake",
        "name": "handwritten.blog",
        "state": "on_stand",
        "direction": "Help readers discover writing",
        "finished_when": None,
        "raw": {
            "id": "cake",
            "shortLink": "cake",
            "name": "handwritten.blog",
            "desc": "unchanged",
        },
    }


def issue(reference: str, body: str = "Issue body") -> dict:
    return {
        "id": "example/blog#7",
        "url": reference,
        "name": "Implementation issue",
        "raw": {
            "title": "Implementation issue",
            "url": reference,
            "state": "OPEN",
            "body": body,
        },
    }


def portfolio_for(cake):
    portfolio = Mock()
    portfolio.snapshot.return_value = {"anything": True}
    portfolio._cake_record.return_value = cake
    portfolio._trello_role.return_value = (
        {"id": "plate", "name": "Plate"},
        {"eating": {"id": "eating", "name": "Eating"}},
    )
    return portfolio


class SlicingTest(unittest.TestCase):
    def test_adopt_previews_assigning_a_parent_without_changing_membership(self) -> None:
        cake = parent()
        portfolio = portfolio_for(cake)
        card = {
            "id": "slice",
            "url": "https://trello.com/c/slice",
            "shortLink": "slice",
            "idBoard": "plate",
            "idList": "eating",
            "name": "Orb: /grill-me session",
            "desc": "",
            "closed": False,
            "pos": 1,
        }
        portfolio.trello.locate_card.return_value = card
        slicer = CakeSlicer(portfolio)

        result = slicer.adopt(
            cake["url"],
            card["url"],
            title="Orb: Complete a /grill-me session",
            outcome="The open design decisions are stress-tested",
            success="One next Slice is recommended",
        )

        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["write"]["action"], "adopt_parentless_plate_card")
        self.assertIn("Cake: https://trello.com/c/cake", result["write"]["body"])
        self.assertIn("Disposition: Current", result["write"]["body"])
        portfolio.trello.update_card.assert_not_called()

    def test_adopt_refuses_to_reparent_an_existing_slice(self) -> None:
        cake = parent()
        portfolio = portfolio_for(cake)
        portfolio.trello.locate_card.return_value = {
            "id": "slice",
            "url": "https://trello.com/c/slice",
            "shortLink": "slice",
            "idBoard": "plate",
            "idList": "eating",
            "name": "Existing Slice",
            "desc": format_slice_contract(
                "https://trello.com/c/another-cake", "Outcome", "Success"
            ),
            "closed": False,
            "pos": 1,
        }
        slicer = CakeSlicer(portfolio)

        with self.assertRaisesRegex(CakeError, "cannot reparent"):
            slicer.adopt(
                cake["url"],
                "https://trello.com/c/slice",
                title="New title",
                outcome="New outcome",
                success="New success",
            )

        portfolio.trello.update_card.assert_not_called()

    def test_matching_adopt_token_updates_only_the_plate_card_contract(self) -> None:
        cake = parent()
        portfolio = portfolio_for(cake)
        card = {
            "id": "slice",
            "url": "https://trello.com/c/slice",
            "shortLink": "slice",
            "idBoard": "plate",
            "idList": "eating",
            "name": "Orb: /grill-me session",
            "desc": "",
            "closed": False,
            "pos": 1,
        }
        portfolio.trello.locate_card.return_value = card
        slicer = CakeSlicer(portfolio)
        values = {
            "title": "Orb: Complete a /grill-me session",
            "outcome": "The open design decisions are stress-tested",
            "success": "One next Slice is recommended",
        }
        preview = slicer.adopt(cake["url"], card["url"], **values)
        portfolio.trello.update_card.return_value = {
            **card,
            "name": preview["write"]["title"],
            "desc": preview["write"]["body"],
        }

        result = slicer.adopt(
            cake["url"],
            card["url"],
            **values,
            confirmation_token=preview["confirmation_token"],
        )

        self.assertEqual(result["status"], "adopted")
        kwargs = portfolio.trello.update_card.call_args.kwargs
        self.assertEqual(set(kwargs), {"name", "description"})
        self.assertIn("Disposition: Current", kwargs["description"])
    def test_create_always_previews_one_archived_plate_card(self) -> None:
        cake = parent()
        portfolio = portfolio_for(cake)
        slicer = CakeSlicer(portfolio)
        result = slicer.create(
            cake["url"],
            title="handwritten.blog: Discovery feed",
            outcome="Readers can discover posts",
            success="The feed lists every published post",
        )
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["write"]["action"], "create_archived_plate_card")
        self.assertIn("Cake: https://trello.com/c/cake", result["write"]["body"])
        self.assertEqual(result["delivery_writes"], [])
        portfolio.trello.create_card.assert_not_called()

    def test_stale_create_token_does_not_write(self) -> None:
        cake = parent()
        portfolio = portfolio_for(cake)
        slicer = CakeSlicer(portfolio)
        with self.assertRaisesRegex(CakeError, "approval is stale"):
            slicer.create(
                cake["url"],
                title="handwritten.blog: Discovery feed",
                outcome="Readers can discover posts",
                success="The feed lists every published post",
                confirmation_token="stale",
            )
        portfolio.trello.create_card.assert_not_called()

    def test_matching_create_token_writes_and_archives_one_plate_card(self) -> None:
        cake = parent()
        portfolio = portfolio_for(cake)
        created = {
            "id": "slice",
            "url": "https://trello.com/c/slice",
            "shortLink": "slice",
            "name": "Piano: First scale",
            "desc": format_slice_contract(cake["url"], "Play one scale", "It is recorded"),
            "closed": False,
        }
        archived = {**created, "closed": True}
        portfolio.trello.create_card.return_value = created
        portfolio.trello.update_card.return_value = archived
        slicer = CakeSlicer(portfolio)
        values = {
            "title": "Piano: First scale",
            "outcome": "Play one scale",
            "success": "It is recorded",
        }
        preview = slicer.create(cake["url"], **values)
        result = slicer.create(
            cake["url"], **values, confirmation_token=preview["confirmation_token"]
        )
        self.assertEqual(result["slice"]["canonical_state"], "archived")
        portfolio.trello.update_card.assert_called_once_with("slice", closed=True)
        self.assertNotIn("next_slice", result)

    def test_create_with_github_issue_writes_reciprocal_backlink(self) -> None:
        cake = parent()
        issue_url = "https://github.com/example/blog/issues/7"
        portfolio = portfolio_for(cake)
        portfolio.github.issue.return_value = issue(issue_url)
        created = {
            "id": "slice",
            "url": "https://trello.com/c/slice",
            "shortLink": "slice",
            "name": "Discovery feed",
            "desc": format_slice_contract(
                cake["url"],
                "Readers can discover posts",
                "The feed lists every published post",
                github_issue=issue_url,
            ),
            "closed": False,
        }
        portfolio.trello.create_card.return_value = created
        portfolio.trello.update_card.return_value = {**created, "closed": True}
        slicer = CakeSlicer(portfolio)
        values = {
            "title": "Discovery feed",
            "outcome": "Readers can discover posts",
            "success": "The feed lists every published post",
            "github_issue": issue_url,
        }
        preview = slicer.create(cake["url"], **values)
        self.assertEqual(preview["delivery_writes"][0]["issue"], issue_url)
        slicer.create(
            cake["url"], **values, confirmation_token=preview["confirmation_token"]
        )
        body = portfolio.github.update_issue.call_args.kwargs["body"]
        self.assertIn("Cake Slice: https://trello.com/c/slice", body)

    def test_updating_current_plate_slice_preserves_membership_and_link(self) -> None:
        cake = parent()
        issue_url = "https://github.com/example/blog/issues/7"
        portfolio = portfolio_for(cake)
        portfolio.github.issue.return_value = issue(issue_url)
        card = {
            "id": "slice",
            "url": "https://trello.com/c/slice",
            "shortLink": "slice",
            "idBoard": "plate",
            "idList": "eating",
            "name": "Old title",
            "desc": format_slice_contract(
                cake["url"], "Old outcome", "Old success", github_issue=issue_url
            ),
            "closed": False,
            "pos": 1,
        }
        portfolio.trello.locate_card.return_value = card
        portfolio.trello.update_card.return_value = card
        slicer = CakeSlicer(portfolio)
        values = {
            "title": "New title",
            "outcome": "New outcome",
            "success": "New success",
            "github_issue": issue_url,
        }
        preview = slicer.update(cake["url"], card["url"], **values)
        slicer.update(
            cake["url"],
            card["url"],
            **values,
            confirmation_token=preview["confirmation_token"],
        )
        kwargs = portfolio.trello.update_card.call_args.kwargs
        self.assertEqual(set(kwargs), {"name", "description"})
        self.assertIn("Disposition: Current", kwargs["description"])
        self.assertIn(f"GitHub issue: {issue_url}", kwargs["description"])
        self.assertIn(
            "Cake Slice: https://trello.com/c/slice",
            portfolio.github.update_issue.call_args.kwargs["body"],
        )


if __name__ == "__main__":
    unittest.main()
