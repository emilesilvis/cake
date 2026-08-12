from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class SkillInstructionTest(unittest.TestCase):
    def test_session_shaped_slice_does_not_invoke_named_skill(self) -> None:
        skill = (REPOSITORY_ROOT / "skills" / "cake-slice" / "SKILL.md").read_text()

        self.assertIn("does not invoke it", skill)
        self.assertIn("define the durable result and finish boundary", skill)
        self.assertIn("only when the user's current request separately asks", skill)


if __name__ == "__main__":
    unittest.main()
