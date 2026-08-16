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

    def test_parked_previous_slice_protocol_is_shared_across_skills(self) -> None:
        prioritise = (
            REPOSITORY_ROOT / "skills" / "cake-prioritise" / "SKILL.md"
        ).read_text()
        slicing = (
            REPOSITORY_ROOT / "skills" / "cake-slice" / "SKILL.md"
        ).read_text()
        doctor = (
            REPOSITORY_ROOT / "skills" / "cake-doctor" / "SKILL.md"
        ).read_text()

        self.assertIn("Previous slice:", prioritise)
        self.assertIn("Previous slice:", slicing)
        self.assertIn("Previous Slice", doctor)


if __name__ == "__main__":
    unittest.main()
