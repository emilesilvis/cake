from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "cake-prioritise"
    / "scripts"
    / "portfolio.py"
)
SPEC = importlib.util.spec_from_file_location("portfolio", SCRIPT)
portfolio = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(portfolio)


class PortfolioTest(unittest.TestCase):
    def test_config_set_updates_only_supplied_values(self) -> None:
        existing = {
            "version": 1,
            "repositories": {},
            "portfolio": {"projects_board": "Projects", "priority": "Ship"},
        }
        args = SimpleNamespace(
            projects_board=None,
            backlog_board="Backlog",
            priority=None,
        )
        with patch.object(portfolio.common, "load_config", return_value=existing), patch.object(
            portfolio.common, "save_config"
        ) as save, patch.object(portfolio, "config_status", return_value={"ok": True}):
            result = portfolio.config_set(args)
        self.assertEqual(result, {"ok": True})
        saved = save.call_args.args[0]
        self.assertEqual(saved["portfolio"]["projects_board"], "Projects")
        self.assertEqual(saved["portfolio"]["backlog_board"], "Backlog")
        self.assertEqual(saved["portfolio"]["priority"], "Ship")

    def test_board_snapshot_classifies_project_lists(self) -> None:
        board = {"id": "projects", "name": "Projects", "url": "https://trello.test/projects"}
        lists = [
            {"id": "active", "name": "Active: Projects"},
            {"id": "next", "name": "Next: Projects"},
            {"id": "tasks", "name": "Tasks"},
            {"id": "done", "name": "Done"},
            {"id": "failed", "name": "Failed/Parked"},
        ]
        cards = [
            {"id": "a", "idList": "active", "name": "Active project"},
            {"id": "n", "idList": "next", "name": "Next project"},
            {"id": "t", "idList": "tasks", "name": "Small task"},
            {"id": "d", "idList": "done", "name": "Done project"},
            {"id": "f", "idList": "failed", "name": "Parked project"},
        ]
        with patch.object(portfolio, "find_board", return_value=board), patch.object(
            portfolio.common, "api", side_effect=[lists, cards]
        ):
            result = portfolio.board_snapshot("Projects", "projects")
        self.assertEqual([card["name"] for card in result["candidates"]], ["Active project", "Next project"])
        self.assertEqual([card["name"] for card in result["active"]], ["Active project"])
        self.assertEqual([card["name"] for card in result["capacity_constraints"]], ["Small task"])
        self.assertEqual(sum(item["count"] for item in result["exclusions"]), 2)

    def test_backlog_keeps_every_open_list_as_candidate(self) -> None:
        board = {"id": "backlog", "name": "Backlog", "url": "https://trello.test/backlog"}
        lists = [
            {"id": "blog", "name": "Blog"},
            {"id": "products", "name": "Products"},
        ]
        cards = [
            {"id": "b", "idList": "blog", "name": "Article"},
            {"id": "p", "idList": "products", "name": "Product"},
        ]
        with patch.object(portfolio, "find_board", return_value=board), patch.object(
            portfolio.common, "api", side_effect=[lists, cards]
        ):
            result = portfolio.board_snapshot("Backlog", "backlog")
        self.assertEqual([card["name"] for card in result["candidates"]], ["Article", "Product"])
        self.assertEqual(result["capacity_constraints"], [])
        self.assertEqual(result["exclusions"], [])

    def test_backlog_excludes_completed_work_when_present(self) -> None:
        board = {"id": "backlog", "name": "Backlog", "url": "https://trello.test/backlog"}
        lists = [
            {"id": "blog", "name": "Blog"},
            {"id": "done", "name": "Done"},
        ]
        cards = [
            {"id": "b", "idList": "blog", "name": "Article"},
            {"id": "d", "idList": "done", "name": "Old idea"},
        ]
        with patch.object(portfolio, "find_board", return_value=board), patch.object(
            portfolio.common, "api", side_effect=[lists, cards]
        ):
            result = portfolio.board_snapshot("Backlog", "backlog")
        self.assertEqual([card["name"] for card in result["candidates"]], ["Article"])
        self.assertEqual(result["exclusions"][0]["count"], 1)

    def test_snapshot_requires_priority_confirmation_and_current_wip_limit(self) -> None:
        config = {
            "projects_board": "Projects",
            "backlog_board": "Backlog",
            "priority": "Finish active products",
        }
        projects = {
            "board": {"id": "projects", "name": "Projects"},
            "candidates": [{"name": "A"}],
            "capacity_constraints": [{"name": "Task"}],
            "active": [{"name": "A"}, {"name": "B"}],
            "exclusions": [{"list": "Done", "count": 4}],
        }
        backlog = {
            "board": {"id": "backlog", "name": "Backlog"},
            "candidates": [{"name": "C"}],
            "capacity_constraints": [],
            "active": [],
            "exclusions": [],
        }
        with patch.object(portfolio, "portfolio_config", return_value=config), patch.object(
            portfolio, "board_snapshot", side_effect=[projects, backlog]
        ), patch.object(
            portfolio, "plugin_status", return_value={"list_limits_plugin_present": True}
        ):
            result = portfolio.snapshot()
        self.assertTrue(result["priority_needs_confirmation"])
        self.assertEqual(result["wip"]["active_count"], 2)
        self.assertIsNone(result["wip"]["limit"])
        self.assertTrue(result["wip"]["needs_current_limit"])
        self.assertEqual([card["name"] for card in result["candidates"]], ["A", "C"])


if __name__ == "__main__":
    unittest.main()
