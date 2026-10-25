"""D-234: an approval's audience may be every active employee ("*"), still an envelope."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import pac, registry  # noqa: E402


class Audience(unittest.TestCase):
    def test_permits(self):
        self.assertTrue(registry.permits(None, "a"))
        self.assertTrue(registry.permits(["*"], "anyone"))
        self.assertTrue(registry.permits(["a"], "a"))
        self.assertFalse(registry.permits(["a"], "b"))
        self.assertFalse(registry.permits([], "a"))

    def test_everyone_envelope_keeps_reviewed_action_and_constraint(self):
        spec = {"allowed_principals": ["*"], "tools": {"read": "r"}, "intake_id": "i",
                "parameter_constraints": {"read": {"type": "object"}}, "valid_until": "2099-01-01T00:00:00+00:00"}
        with patch.object(registry, "server", lambda server: spec):
            self.assertTrue(pac.scope({"token": "someone"}, "s", "read", "r", [], {})["allowed"])
            self.assertFalse(pac.scope({"token": "someone"}, "s", "read", "w", [], {})["allowed"])
            self.assertFalse(pac.scope({"token": "someone"}, "s", "missing", "r", [], {})["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
