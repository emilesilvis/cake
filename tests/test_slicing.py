from __future__ import annotations

import unittest
from unittest.mock import Mock

from cake_core.domain import CakeError, format_slice_contract
from cake_core.slicing import CakeSlicer


def parent(source="github:example/blog?query=label%3Acake-slice"):
    return {
        "id": "cake",
        "url": "https://trello.test/c/cake",
        "name": "handwritten.blog",
        "state": "on_stand",
        "direction": "Help readers discover writing",
        "finished_when": None,
        "slice_source": source,
        "raw": {"id": "cake", "name": "handwritten.blog", "desc": "unchanged"},
    }


def portfolio_for(cake):
    portfolio = Mock()
    portfolio.snapshot.return_value = {"anything": True}
    portfolio._cake_record.return_value = cake
    return portfolio


class SlicingTest(unittest.TestCase):
    def test_github_create_previews_without_writing(self) -> None:
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
        self.assertEqual(result["write"]["labels"], ["cake-slice"])
        self.assertIn(f"Cake: {cake['url']}", result["write"]["body"])
        portfolio.github.create_issue.assert_not_called()

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
        portfolio.github.create_issue.assert_not_called()

    def test_create_rejects_a_query_it_cannot_safely_satisfy(self) -> None:
        cake = parent("github:example/blog?query=assignee%3Ame")
        portfolio = portfolio_for(cake)
        slicer = CakeSlicer(portfolio)
        with self.assertRaisesRegex(CakeError, "cannot guarantee writes remain"):
            slicer.create(
                cake["url"],
                title="handwritten.blog: Discovery feed",
                outcome="Readers can discover posts",
                success="The feed lists every published post",
            )
        portfolio.github.create_issue.assert_not_called()

    def test_matching_create_token_writes_one_canonical_issue(self) -> None:
        cake = parent()
        portfolio = portfolio_for(cake)
        portfolio.github.create_issue.return_value = {
            "url": "https://github.com/example/blog/issues/1"
        }
        slicer = CakeSlicer(portfolio)
        values = {
            "title": "handwritten.blog: Discovery feed",
            "outcome": "Readers can discover posts",
            "success": "The feed lists every published post",
        }
        preview = slicer.create(cake["url"], **values)
        result = slicer.create(
            cake["url"], **values, confirmation_token=preview["confirmation_token"]
        )
        self.assertEqual(result["status"], "created")
        portfolio.github.create_issue.assert_called_once()

    def test_plate_create_is_archived_and_never_nominated(self) -> None:
        cake = parent("plate")
        portfolio = portfolio_for(cake)
        portfolio._trello_role.return_value = (
            {"id": "plate", "name": "Plate"},
            {"eating": {"id": "eating", "name": "Eating"}},
        )
        created = {
            "id": "slice",
            "url": "https://trello.test/c/slice",
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

    def test_updating_current_plate_slice_preserves_membership(self) -> None:
        cake = parent("plate")
        portfolio = portfolio_for(cake)
        portfolio._trello_role.return_value = (
            {"id": "plate", "name": "Plate"},
            {"eating": {"id": "eating", "name": "Eating"}},
        )
        card = {
            "id": "slice",
            "url": "https://trello.test/c/slice",
            "idBoard": "plate",
            "idList": "eating",
            "name": "Old title",
            "desc": format_slice_contract(cake["url"], "Old outcome", "Old success"),
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
        }
        preview = slicer.update(cake["url"], card["url"], **values)
        slicer.update(
            cake["url"], card["url"], **values, confirmation_token=preview["confirmation_token"]
        )
        kwargs = portfolio.trello.update_card.call_args.kwargs
        self.assertEqual(set(kwargs), {"name", "description"})
        self.assertIn("Disposition: Current", kwargs["description"])


if __name__ == "__main__":
    unittest.main()
