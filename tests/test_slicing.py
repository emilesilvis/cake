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
        "repository": None,
        "slice_index": [],
        "current_slice_links": [],
        "current_slices": [],
        "previous_slice": None,
        "next_slice": None,
        "available_slices": [],
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
        "adapter": "github",
        "canonical_state": "open",
        "cake": "https://trello.com/c/cake",
        "outcome": "Readers can discover posts",
        "success": "The feed lists every published post",
        "not_included": None,
        "plate": None,
        "disposition": "candidate",
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
    def test_sync_available_lists_every_viable_inactive_slice_on_the_cake(self) -> None:
        cake = parent()
        first = {
            "id": "one",
            "url": "https://trello.com/c/one",
            "name": "Blog: First",
            "adapter": "plate",
            "cake": cake["url"],
            "outcome": "First exists",
            "success": "First is observable",
            "disposition": "candidate",
            "raw": {"shortLink": "one"},
        }
        second = {
            "id": "two",
            "url": "https://trello.com/c/two",
            "name": "Blog: Second",
            "adapter": "plate",
            "cake": cake["url"],
            "outcome": "Second exists",
            "success": "Second is observable",
            "disposition": "paused",
            "raw": {"shortLink": "two"},
        }
        portfolio = portfolio_for(cake)
        portfolio.snapshot.return_value = {"slice_catalog": [second, first]}
        slicer = CakeSlicer(portfolio)

        preview = slicer.sync_available(cake["url"])

        self.assertEqual(
            preview["write"]["available_slices"],
            ["https://trello.com/c/one", "https://trello.com/c/two"],
        )
        self.assertIn(
            "**Available slices:** https://trello.com/c/one",
            preview["write"]["target_body"],
        )
        slicer.sync_available(
            cake["url"], confirmation_token=preview["confirmation_token"]
        )
        self.assertEqual(
            portfolio._update_cake.call_args.kwargs["available_slices"],
            ["https://trello.com/c/one", "https://trello.com/c/two"],
        )

    def test_sync_available_repairs_previous_slice_navigation_for_a_parked_cake(self) -> None:
        cake = parent()
        cake["state"] = "parked"
        finished = {
            "id": "finished",
            "url": "https://trello.com/c/finished",
            "name": "Blog: Finished result",
            "adapter": "plate",
            "cake": cake["url"],
            "outcome": "A result exists",
            "success": "The result is observable",
            "disposition": "finished",
            "raw": {
                "shortLink": "finished",
                "dateLastActivity": "2026-08-16T09:00:00.000Z",
            },
        }
        portfolio = portfolio_for(cake)
        portfolio.snapshot.return_value = {"slice_catalog": [finished], "plate": {}}
        slicer = CakeSlicer(portfolio)

        preview = slicer.sync_available(cake["url"])

        self.assertEqual(preview["write"]["previous_slice"], finished["url"])
        self.assertIn(
            "**Previous slice:** https://trello.com/c/finished",
            preview["write"]["target_body"],
        )
        slicer.sync_available(
            cake["url"], confirmation_token=preview["confirmation_token"]
        )
        self.assertEqual(
            portfolio._update_cake.call_args.kwargs["previous_slice"],
            finished["url"],
        )

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
        self.assertEqual(result["write"]["action"], "adopt_parentless_plate_slice")
        self.assertIn("**Cake:** https://trello.com/c/cake", result["write"]["body"])
        self.assertIn("**Disposition:** Current", result["write"]["body"])
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
        self.assertIn("**Disposition:** Current", kwargs["description"])
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
        self.assertEqual(result["write"]["action"], "create_archived_plate_slice")
        self.assertIn("**Cake:** https://trello.com/c/cake", result["write"]["body"])
        self.assertIn("\n\n**Outcome:**", result["write"]["body"])
        self.assertIn("<created Trello Slice URL>", result["cake_write"]["target_body"])
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

    def test_repository_backed_create_writes_github_issue_and_makes_it_available(self) -> None:
        cake = parent()
        cake["repository"] = "https://github.com/example/blog"
        issue_url = "https://github.com/example/blog/issues/7"
        portfolio = portfolio_for(cake)
        portfolio.github.create_issue.return_value = issue(issue_url)
        slicer = CakeSlicer(portfolio)
        values = {
            "title": "Discovery feed",
            "outcome": "Readers can discover posts",
            "success": "The feed lists every published post",
        }
        preview = slicer.create(cake["url"], **values)
        self.assertEqual(preview["provider"], "github")
        self.assertEqual(preview["write"]["action"], "create_github_slice_issue")
        self.assertIn("Cake: https://trello.com/c/cake", preview["write"]["body"])
        self.assertNotIn("**Cake:**", preview["write"]["body"])

        result = slicer.create(
            cake["url"], **values, confirmation_token=preview["confirmation_token"]
        )
        portfolio.github.ensure_label.assert_called_once_with("example/blog", "cake-slice")
        portfolio.github.create_issue.assert_called_once()
        portfolio.trello.create_card.assert_not_called()
        self.assertEqual(result["cake_available_slices"], [issue_url])
        self.assertEqual(
            portfolio._update_cake.call_args.kwargs["available_slices"], [issue_url]
        )

    def test_updating_current_github_slice_preserves_plate_backlink(self) -> None:
        cake = parent()
        cake["repository"] = "https://github.com/example/blog"
        issue_url = "https://github.com/example/blog/issues/7"
        plate_url = "https://trello.com/c/projection"
        portfolio = portfolio_for(cake)
        current_issue = issue(issue_url)
        current_issue.update(
            {
                "name": "Old title",
                "outcome": "Old outcome",
                "success": "Old success",
                "plate": plate_url,
                "disposition": "current",
            }
        )
        portfolio._candidate_record.return_value = current_issue
        portfolio.github.update_issue.return_value = {
            **current_issue,
            "name": "New title",
            "outcome": "New outcome",
            "success": "New success",
        }
        slicer = CakeSlicer(portfolio)
        values = {
            "title": "New title",
            "outcome": "New outcome",
            "success": "New success",
        }
        preview = slicer.update(cake["url"], issue_url, **values)
        slicer.update(
            cake["url"],
            issue_url,
            **values,
            confirmation_token=preview["confirmation_token"],
        )
        body = portfolio.github.update_issue.call_args.kwargs["body"]
        self.assertIn("Disposition: Current", body)
        self.assertIn(f"Plate: {plate_url}", body)
        portfolio.trello.update_card.assert_not_called()

    def test_repository_attachment_preserves_terminal_trello_previous_slice(self) -> None:
        cake = parent()
        cake["state"] = "parked"
        cake["previous_slice"] = "https://trello.com/c/finished"
        finished = {
            "id": "finished",
            "url": "https://trello.com/c/finished",
            "name": "Cake: Finished behavior",
            "adapter": "plate",
            "canonical_state": "archived",
            "cake": cake["url"],
            "outcome": "The behavior exists",
            "success": "The behavior is verified",
            "disposition": "finished",
            "raw": {
                "shortLink": "finished",
                "dateLastActivity": "2026-08-16T09:00:00.000Z",
            },
        }
        portfolio = portfolio_for(cake)
        portfolio.snapshot.return_value = {
            "slice_catalog": [finished],
            "source_health": [],
        }
        portfolio.github.slices.return_value = []
        slicer = CakeSlicer(portfolio)

        preview = slicer.attach_repository(
            cake["url"], repository="example/cake"
        )

        self.assertEqual(preview["status"], "preview")
        self.assertIn(
            "**Repository:** https://github.com/example/cake",
            preview["write"]["target_body"],
        )
        self.assertIn(
            "**Previous slice:** https://trello.com/c/finished",
            preview["write"]["target_body"],
        )

        result = slicer.attach_repository(
            cake["url"],
            repository="example/cake",
            confirmation_token=preview["confirmation_token"],
        )

        self.assertEqual(result["status"], "attached")
        cake_update = portfolio._update_cake.call_args.kwargs
        self.assertEqual(cake_update["repository"], "https://github.com/example/cake")
        self.assertEqual(cake_update["previous_slice"], finished["url"])

    def test_repository_attachment_refuses_unfinished_trello_slice(self) -> None:
        cake = parent()
        candidate = {
            "id": "candidate",
            "url": "https://trello.com/c/candidate",
            "adapter": "plate",
            "cake": cake["url"],
            "outcome": "A result exists",
            "success": "The result is visible",
            "disposition": "candidate",
        }
        portfolio = portfolio_for(cake)
        portfolio.snapshot.return_value = {
            "slice_catalog": [candidate],
            "source_health": [],
        }
        slicer = CakeSlicer(portfolio)

        with self.assertRaisesRegex(CakeError, "Migrate every unfinished"):
            slicer.attach_repository(cake["url"], repository="example/cake")

        portfolio._update_cake.assert_not_called()

    def test_migration_previews_all_cross_provider_writes_before_applying(self) -> None:
        cake = parent()
        cake["next_slice"] = "https://trello.com/c/slice"
        source = {
            "id": "slice",
            "url": "https://trello.com/c/slice",
            "shortLink": "slice",
            "name": "Blog: Rewrite five posts",
            "adapter": "plate",
            "canonical_state": "archived",
            "cake": cake["url"],
            "outcome": "Five posts read naturally",
            "success": "All five pass the checker",
            "not_included": None,
            "disposition": "candidate",
            "raw": {"shortLink": "slice"},
        }
        finished = {
            **source,
            "id": "finished",
            "url": "https://trello.com/c/finished",
            "disposition": "finished",
        }
        portfolio = portfolio_for(cake)
        portfolio.snapshot.return_value = {"slice_catalog": [finished, source]}
        portfolio._candidate_record.return_value = source
        portfolio.github.slices.return_value = []
        slicer = CakeSlicer(portfolio)

        preview = slicer.migrate_to_github(
            cake["url"], source["url"], repository="example/blog"
        )

        self.assertEqual([write["action"] for write in preview["writes"]], [
            "create_github_slice_issue",
            "supersede_trello_slice",
            "set_cake_slice_provider",
        ])
        self.assertIn("<created GitHub Slice URL>", preview["writes"][2]["target_body"])
        portfolio.github.create_issue.assert_not_called()
        portfolio.trello.update_card.assert_not_called()

        issue_url = "https://github.com/example/blog/issues/9"
        portfolio.github.create_issue.return_value = issue(issue_url)
        result = slicer.migrate_to_github(
            cake["url"],
            source["url"],
            repository="example/blog",
            confirmation_token=preview["confirmation_token"],
        )

        migration_body = portfolio.trello.update_card.call_args.kwargs["description"]
        self.assertIn(f"**Slice:** {issue_url}", migration_body)
        self.assertIn("**Disposition:** Migrated", migration_body)
        self.assertTrue(portfolio.trello.update_card.call_args.kwargs["closed"])
        cake_update = portfolio._update_cake.call_args.kwargs
        self.assertEqual(cake_update["repository"], "https://github.com/example/blog")
        self.assertEqual(cake_update["available_slices"], [])
        self.assertEqual(cake_update["next_slice"], issue_url)
        self.assertEqual(result["status"], "migrated")


if __name__ == "__main__":
    unittest.main()
