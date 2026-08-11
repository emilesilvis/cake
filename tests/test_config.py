from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from cake_core.config import DEFAULT_LISTS, configure, empty_config, normalized_config, save_config


class ConfigTest(unittest.TestCase):
    def test_new_board_configuration_uses_domain_list_names(self) -> None:
        config = configure(
            empty_config(),
            pantry_board="Pantry",
            cake_stand_board="Cake Stand",
            plate_board="Plate",
        )
        self.assertEqual(config["portfolio"]["cake_stand"]["lists"], DEFAULT_LISTS["cake_stand"])
        self.assertEqual(config["portfolio"]["plate"]["lists"], DEFAULT_LISTS["plate"])

    def test_legacy_config_is_reported_without_guessing_a_migration(self) -> None:
        config = normalized_config(
            {
                "version": 1,
                "portfolio": {"projects_board": "Projects", "backlog_board": "Backlog"},
            }
        )
        self.assertTrue(config["legacy"]["detected"])
        self.assertIsNone(config["portfolio"]["cake_stand"])
        self.assertIsNone(config["portfolio"]["plate"])

    def test_save_is_private_and_versioned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cake" / "config.json"
            save_config(empty_config(), path)
            self.assertEqual(json.loads(path.read_text())["version"], 2)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
