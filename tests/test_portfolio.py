from __future__ import annotations

import unittest
from unittest.mock import patch

from cake_core.domain import CakeError, format_cake_contract, format_slice_contract
from cake_core.portfolio import CakePortfolio


class FakeTrello:
    def __init__(self) -> None:
        self.boards = {
            "Pantry": {"id": "pantry", "name": "Pantry", "url": "https://trello.test/b/pantry"},
            "Cake Stand": {"id": "stand", "name": "Cake Stand", "url": "https://trello.test/b/stand"},
            "Plate": {"id": "plate", "name": "Plate", "url": "https://trello.test/b/plate"},
        }
        self.board_lists = {
            "stand": {
                "On the stand": {"id": "on", "name": "On the stand"},
                "Parked": {"id": "parked", "name": "Parked"},
                "Finished": {"id": "finished", "name": "Finished"},
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
        "url": f"https://trello.test/c/{identifier}",
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
    def test_plate_derives_being_eaten_from_a_canonical_slice_with_delivery_link(self) -> None:
        trello = FakeTrello()
        cake_url = "https://trello.test/c/blog"
        issue_url = "https://github.com/example/blog/issues/7"
        trello.board_cards["stand"] = [
            card(
                "blog",
                "stand",
                "on",
                "handwritten.blog",
                format_cake_contract("Help readers discover writing"),
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
        self.assertEqual(active_cake["current_slices"], ["https://trello.test/c/feed"])
        self.assertEqual(result["plate"]["eating"][0]["outcome"], "Readers can discover posts")
        self.assertEqual(result["plate"]["eating"][0]["github_issue"], issue_url)
        self.assertEqual(result["issues"]["errors"], [])

    def test_waiting_cake_derives_waiting_condition(self) -> None:
        trello = FakeTrello()
        cake_url = "https://trello.test/c/piano"
        slice_url = "https://trello.test/c/scales"
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


if __name__ == "__main__":
    unittest.main()
