import json
import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import prepare_lab_capabilities as fixture


class LabValidityTests(unittest.TestCase):
    def test_window_moves_with_runner_date_and_preserves_approved_scope(self):
        source = json.loads(fixture.LAB_CAPABILITIES.read_text(encoding="utf-8"))
        for now in (datetime(2026, 11, 1, tzinfo=UTC), datetime(2030, 1, 1, tzinfo=UTC)):
            result = fixture.prepare(source, now)
            for original, current in zip(source["capabilities"], result["capabilities"], strict=True):
                self.assertEqual(datetime.fromisoformat(current["valid_from"]), now - timedelta(minutes=1))
                self.assertEqual(datetime.fromisoformat(current["valid_until"]), now + timedelta(days=1))
                self.assertEqual({k: v for k, v in original.items() if k not in ("valid_from", "valid_until")},
                                 {k: v for k, v in current.items() if k not in ("valid_from", "valid_until")})
            self.assertNotEqual(source, result)
        self.assertEqual(source, json.loads(fixture.LAB_CAPABILITIES.read_text(encoding="utf-8")))

    def test_local_execution_is_refused_before_writing(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(fixture.Path, "write_text") as write:
            with self.assertRaises(SystemExit):
                fixture.main()
            write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
