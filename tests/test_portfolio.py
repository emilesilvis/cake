from __future__ import annotations

import unittest
from unittest.mock import patch

from cake_core.domain import CakeError, format_cake_contract, format_slice_contract
from cake_core.portfolio import CakePortfolio
from cake_core.providers import TrelloAdapter


class FakeTrello:
    def __init__(self) -> None:
        self.boards = {
            "Pantry": {"id": "pantry", "name": "Pantry", "url": "https://trello.com/b/pantry"},
            "Cake Stand": {"id": "stand", "name": "Cake Stand", "url": "https://trello.com/b/stand"},
            "Plate": {"id": "plate", "name": "Plate", "url": "https://trello.com/b/plate"},
        }
        self.board_lists = {
            "stand": {
                "On the stand": {"id": "on", "name": "On the stand"},
                "Parked": {"id": "parked", "name": "Parked"},
                "Finished": {"id": "finished", "name": "Finished"},
                "Rhythms / capacity": {"id": "capacity", "name": "Rhythms / capacity"},
            },
            "plate": {
                "Eating": {"id": "eating", "name": "Eating"},
                "Blocked": {"id": "blocked", "name": "Blocked"},
            },
        }
        self.board_cards = {"pantry": [], "stand": [], "plate": []}
        self.writes: list[tuple] = []

    def board(self, reference):
        return self.boards[reference]

    def list(self, board, reference):
        return self.board_lists[board["id"]][reference]

    def cards(self, board, include_archived=False):
        cards = self.board_cards[board["id"]]
        return list(cards) if include_archived else [card for card in cards if not card.get("closed")]

    def card(self, reference):
        for cards in self.board_cards.values():
            for card in cards:
                if reference in {card["id"], card.get("url")}:
                    return card
        raise CakeError("missing card")

    def plugin_status(self, board):
        return {"list_limits_plugin_present": True}

    def update_card(self, *args, **kwargs):
        self.writes.append((args, kwargs))
        return {"id": args[0], **kwargs}


class FakeGitHub:
    pass


def card(identifier, board, list_id, name, description, *, closed=False, position=1):
    return {
        "id": identifier,
        "url": f"https://trello.com/c/{identifier}",
        "shortLink": identifier,
        "idBoard": board,
        "idList": list_id,
        "name": name,
        "desc": description,
        "closed": closed,
        "pos": position,
    }


def config():
    return {
        "version": 2,
        "portfolio": {
            "priority": "Publish useful work",
            "pantry": {"adapter": "trello", "board": "Pantry"},
            "cake_stand": {
                "adapter": "trello",
                "board": "Cake Stand",
                "lists": {
                    "on_stand": "On the stand",
                    "parked": "Parked",
                    "finished": "Finished",
                },
            },
            "plate": {
                "adapter": "trello",
                "board": "Plate",
                "lists": {"eating": "Eating", "blocked": "Blocked"},
            },
            "capacity_sources": [],
        },
    }


class PortfolioTest(unittest.TestCase):
    def test_archived_cake_is_hidden_but_resolves_an_archived_slice_parent(self) -> None:
        trello = FakeTrello()
        cake_url = "https://trello.com/c/old-routine"
        trello.board_cards["stand"] = [
            card(
                "old-routine",
                "stand",
                "parked",
                "Old routine",
                format_cake_contract("Maintain the former routine"),
                closed=True,
            )
        ]
        trello.board_cards["plate"] = [
            card(
                "old-occurrence",
                "plate",
                "eating",
                "Old routine: occurrence",
                format_slice_contract(
                    cake_url,
                    "One occurrence is complete",
                    "The occurrence happened",
                    disposition="abandoned",
                    reason="Reclassified as recurring capacity",
                ),
                closed=True,
            )
        ]

        result = CakePortfolio(config=config(), trello=trello, github=FakeGitHub()).snapshot()

        self.assertEqual(result["cake_stand"]["parked"], [])
        self.assertEqual([item["name"] for item in result["archived_cakes"]], ["Old routine"])
        self.assertEqual(result["archived_cakes"][0]["former_state"], "parked")
        self.assertEqual(result["issues"]["errors"], [])

    def test_archive_operation_only_closes_the_human_trello_card(self) -> None:
        trello = FakeTrello()
        trello.board_cards["stand"] = [
            card(
                "old-routine",
                "stand",
                "parked",
                "Old routine",
                format_cake_contract("Maintain the former routine"),
            )
        ]
        portfolio = CakePortfolio(config=config(), trello=trello, github=FakeGitHub())

        portfolio._execute(
            {"action": "archive_cake", "cake": "https://trello.com/c/old-routine"}
        )

        self.assertEqual(trello.writes, [(('old-routine',), {"closed": True})])

    def test_configured_capacity_list_can_share_the_cake_stand_board(self) -> None:
        trello = FakeTrello()
        trello.board_cards["stand"] = [
            card(
                "gym",
                "stand",
                "capacity",
                "Gym",
                "Cadence: Twice weekly\nLoad: Two sessions per week",
            )
        ]
        value = config()
        value["portfolio"]["capacity_sources"] = [
            {
                "adapter": "trello",
                "board": "Cake Stand",
                "lists": ["Rhythms / capacity"],
            }
        ]

        result = CakePortfolio(config=value, trello=trello, github=FakeGitHub()).snapshot()

        self.assertEqual([item["name"] for item in result["capacity_constraints"]], ["Gym"])
        self.assertEqual(result["cake_stand"]["on_stand"], [])
        self.assertEqual(result["unexpected_records"], [])
        self.assertEqual(result["source_health"], [])

    def test_plate_derives_being_eaten_from_a_canonical_slice_with_delivery_link(self) -> None:
        trello = FakeTrello()
        cake_url = "https://trello.com/c/blog"
        issue_url = "https://github.com/example/blog/issues/7"
        trello.board_cards["stand"] = [
            card(
                "blog",
                "stand",
                "on",
                "handwritten.blog",
                format_cake_contract(
                    "Help readers discover writing",
                    current_slices=["https://trello.com/c/feed"],
                ),
            )
        ]
        trello.board_cards["plate"] = [
            card(
                "feed",
                "plate",
                "eating",
                "handwritten.blog: Discovery feed",
                format_slice_contract(
                    cake_url,
                    "Readers can discover posts",
                    "The feed lists published posts",
                    disposition="current",
                    github_issue=issue_url,
                ),
            )
        ]
        portfolio = CakePortfolio(config=config(), trello=trello, github=FakeGitHub())
        result = portfolio.snapshot()
        active_cake = result["cake_stand"]["on_stand"][0]
        self.assertEqual(active_cake["condition"], "being_eaten")
        self.assertEqual(active_cake["current_slices"], ["https://trello.com/c/feed"])
        self.assertEqual(
            active_cake["current_slice_links"], ["https://trello.com/c/feed"]
        )
        self.assertEqual(result["plate"]["eating"][0]["outcome"], "Readers can discover posts")
        self.assertEqual(result["plate"]["eating"][0]["github_issue"], issue_url)
        self.assertEqual(result["issues"]["errors"], [])

    def test_waiting_cake_derives_waiting_condition(self) -> None:
        trello = FakeTrello()
        cake_url = "https://trello.com/c/piano"
        slice_url = "https://trello.com/c/scales"
        trello.board_cards["stand"] = [
            card(
                "piano",
                "stand",
                "on",
                "Learn piano",
                format_cake_contract("Play freely", next_slice=slice_url),
            )
        ]
        trello.board_cards["plate"] = [
            card(
                "scales",
                "plate",
                "eating",
                "Piano: First scale",
                format_slice_contract(cake_url, "Play one scale", "It is recorded"),
                closed=True,
            )
        ]
        portfolio = CakePortfolio(config=config(), trello=trello, github=FakeGitHub())
        result = portfolio.snapshot()
        self.assertEqual(
            result["cake_stand"]["on_stand"][0]["condition"], "waiting_on_the_stand"
        )
        self.assertEqual(result["plate"]["eating"], [])

    def test_pull_writes_reciprocal_short_links(self) -> None:
        trello = FakeTrello()
        cake_url = "https://trello.com/c/blog/a-long-cake-title"
        slice_url = "https://trello.com/c/feed/a-long-slice-title"
        trello.board_cards["stand"] = [
            card(
                "blog",
                "stand",
                "on",
                "handwritten.blog",
                format_cake_contract("Help readers", next_slice=slice_url),
            )
        ]
        trello.board_cards["stand"][0]["url"] = cake_url
        trello.board_cards["plate"] = [
            card(
                "feed",
                "plate",
                "eating",
                "handwritten.blog: Discovery feed",
                format_slice_contract(cake_url, "Readers find posts", "The feed works"),
                closed=True,
            )
        ]
        trello.board_cards["plate"][0]["url"] = slice_url
        portfolio = CakePortfolio(config=config(), trello=trello, github=FakeGitHub())

        portfolio._execute({"action": "pull", "cake": cake_url, "lane": "eating"})

        slice_write = trello.writes[0][1]
        cake_write = trello.writes[1][1]
        self.assertIn("Cake: https://trello.com/c/blog", slice_write["description"])
        self.assertIn("Current slices: https://trello.com/c/feed", cake_write["description"])
        self.assertNotIn("Next slice:", cake_write["description"])

    def test_exit_replaces_the_last_current_link_with_next_slice(self) -> None:
        trello = FakeTrello()
        cake_url = "https://trello.com/c/blog"
        current_url = "https://trello.com/c/feed"
        next_url = "https://trello.com/c/search"
        trello.board_cards["stand"] = [
            card(
                "blog",
                "stand",
                "on",
                "handwritten.blog",
                format_cake_contract("Help readers", current_slices=[current_url]),
            )
        ]
        trello.board_cards["plate"] = [
            card(
                "feed",
                "plate",
                "eating",
                "handwritten.blog: Discovery feed",
                format_slice_contract(
                    cake_url,
                    "Readers find posts",
                    "The feed works",
                    disposition="current",
                ),
            ),
            card(
                "search",
                "plate",
                "eating",
                "handwritten.blog: Search",
                format_slice_contract(cake_url, "Readers search", "Search works"),
                closed=True,
            ),
        ]
        portfolio = CakePortfolio(config=config(), trello=trello, github=FakeGitHub())

        portfolio._execute(
            {
                "action": "exit",
                "plate_slice": current_url,
                "disposition": "finished",
                "next_slice": next_url,
            }
        )

        cake_write = trello.writes[1][1]
        self.assertIn("Next slice: https://trello.com/c/search", cake_write["description"])
        self.assertNotIn("Current slices:", cake_write["description"])

    def test_apply_rejects_stale_confirmation_before_writing(self) -> None:
        portfolio = CakePortfolio(config=config(), trello=FakeTrello(), github=FakeGitHub())
        with patch.object(
            portfolio,
            "preview",
            return_value={"confirmation_token": "fresh", "capacity_warnings": []},
        ), patch.object(portfolio, "_execute") as execute:
            with self.assertRaisesRegex(CakeError, "invalid or relevant source state changed"):
                portfolio.apply([{"action": "anything"}], "stale")
        execute.assert_not_called()

    def test_apply_requires_explicit_capacity_overage_review(self) -> None:
        portfolio = CakePortfolio(config=config(), trello=FakeTrello(), github=FakeGitHub())
        with patch.object(
            portfolio,
            "preview",
            return_value={"confirmation_token": "fresh", "capacity_warnings": [{"over_by": 1}]},
        ), patch.object(portfolio, "_execute") as execute:
            with self.assertRaisesRegex(CakeError, "explicitly allow"):
                portfolio.apply([{"action": "anything"}], "fresh")
        execute.assert_not_called()


class ProviderTest(unittest.TestCase):
    def test_create_list_uses_the_trello_list_endpoint(self) -> None:
        adapter = TrelloAdapter()
        with patch.object(
            adapter,
            "request",
            return_value={"id": "capacity", "name": "Rhythms / capacity"},
        ) as request:
            result = adapter.create_list("stand", name="Rhythms / capacity")

        self.assertEqual(result["id"], "capacity")
        request.assert_called_once_with(
            "POST",
            "/lists",
            {"idBoard": "stand", "name": "Rhythms / capacity", "pos": "bottom"},
        )


if __name__ == "__main__":
    unittest.main()
