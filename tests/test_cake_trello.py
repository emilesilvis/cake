from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "cake-slice"
    / "scripts"
    / "cake_trello.py"
)
SPEC = importlib.util.spec_from_file_location("cake_trello", SCRIPT)
cake_trello = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(cake_trello)


class CakeTrelloTest(unittest.TestCase):
    def test_description_has_optional_boundary(self) -> None:
        self.assertEqual(
            cake_trello.description("Ship it", "A user can use it", None),
            "Outcome: Ship it\nSuccess: A user can use it",
        )
        self.assertEqual(
            cake_trello.description("Ship it", "A user can use it", "Analytics"),
            "Outcome: Ship it\nSuccess: A user can use it\nNot included: Analytics",
        )

    def test_normalize_remote_unifies_https_and_ssh(self) -> None:
        expected = "https://github.com/emilesilvis/cake"
        self.assertEqual(cake_trello.normalize_remote("git@github.com:emilesilvis/cake.git"), expected)
        self.assertEqual(cake_trello.normalize_remote("https://github.com/EmileSilvis/cake.git"), expected)

    def test_update_requires_token_before_any_write(self) -> None:
        current = {
            "id": "card-id",
            "name": "Cake",
            "desc": "Broad direction",
            "closed": False,
        }
        args = SimpleNamespace(
            card="card-id",
            title="Cake: First slice",
            outcome="One outcome",
            success="Observable success",
            not_included=None,
            apply_token=None,
        )
        with patch.object(cake_trello, "get_card", return_value=current), patch.object(
            cake_trello, "api"
        ) as api:
            result = cake_trello.update_card(args)
        self.assertEqual(result["status"], "preview")
        self.assertRegex(result["confirmation_token"], r"^[0-9a-f]{20}$")
        api.assert_not_called()

    def test_update_rejects_stale_token_without_write(self) -> None:
        current = {
            "id": "card-id",
            "name": "Cake changed",
            "desc": "New direction",
            "closed": False,
        }
        args = SimpleNamespace(
            card="card-id",
            title="Cake: First slice",
            outcome="One outcome",
            success="Observable success",
            not_included=None,
            apply_token="wrong-token",
        )
        with patch.object(cake_trello, "get_card", return_value=current), patch.object(
            cake_trello, "api"
        ) as api:
            with self.assertRaisesRegex(cake_trello.CakeError, "invalid or the card changed"):
                cake_trello.update_card(args)
        api.assert_not_called()

    def test_update_preserves_source_before_mutating(self) -> None:
        current = {
            "id": "card-id",
            "name": "Cake",
            "desc": "Broad direction",
            "closed": False,
        }
        args = SimpleNamespace(
            card="card-id",
            title="Cake: First slice",
            outcome="One outcome",
            success="Observable success",
            not_included="Prioritise",
            apply_token=None,
        )
        payload = cake_trello.update_payload(args, current)
        args.apply_token = cake_trello.token_for(payload)
        updated = {"id": "card-id", **payload["target"], "url": "https://trello.test/card"}
        with patch.object(cake_trello, "get_card", return_value=current), patch.object(
            cake_trello, "api", side_effect=[{"id": "comment"}, updated]
        ) as api:
            result = cake_trello.update_card(args)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(api.call_args_list[0].args[0:2], ("POST", "/cards/card-id/actions/comments"))
        self.assertEqual(api.call_args_list[1].args[0:2], ("PUT", "/cards/card-id"))

    def test_create_requires_token_before_write(self) -> None:
        args = SimpleNamespace(
            repo=".",
            title="Cake: First slice",
            outcome="One outcome",
            success="Observable success",
            not_included=None,
            apply_token=None,
        )
        destination = {
            "remote": "https://github.com/emilesilvis/cake",
            "board_id": "board-id",
            "board_name": "Projects",
            "list_id": "list-id",
            "list_name": "Active: Projects",
        }
        with patch.object(cake_trello, "config_get", return_value=destination), patch.object(
            cake_trello, "api"
        ) as api:
            result = cake_trello.create_card(args)
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["destination"]["list_name"], "Active: Projects")
        api.assert_not_called()

    def test_create_applies_only_matching_preview(self) -> None:
        args = SimpleNamespace(
            repo=".",
            title="Cake: First slice",
            outcome="One outcome",
            success="Observable success",
            not_included=None,
            apply_token=None,
        )
        destination = {
            "remote": "https://github.com/emilesilvis/cake",
            "board_id": "board-id",
            "board_name": "Projects",
            "list_id": "list-id",
            "list_name": "Active: Projects",
        }
        payload = cake_trello.create_payload(args, destination)
        args.apply_token = cake_trello.token_for(payload)
        created = {
            "id": "card-id",
            "name": "Cake: First slice",
            "desc": "Outcome: One outcome\nSuccess: Observable success",
            "url": "https://trello.test/card",
        }
        with patch.object(cake_trello, "config_get", return_value=destination), patch.object(
            cake_trello, "api", return_value=created
        ) as api:
            result = cake_trello.create_card(args)
        self.assertEqual(result["status"], "created")
        api.assert_called_once_with(
            "POST",
            "/cards",
            {
                "idList": "list-id",
                "name": "Cake: First slice",
                "desc": "Outcome: One outcome\nSuccess: Observable success",
                "pos": "top",
            },
        )


if __name__ == "__main__":
    unittest.main()
