"""Small checks for the live-model bootstrap, without contacting a provider."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab import live_setup


class LiveSetupTest(unittest.TestCase):
    def test_config_stays_local_and_rejects_test_double(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("AGENT_JWT_PUBLIC_KEY=keep-me\n", encoding="utf-8")
            config = {"MCP_SCAN_BASE_URL": "https://api.example.invalid/v1",
                      "MCP_SCAN_MODEL": "example/model", "MCP_SCAN_API_KEY": "test-secret-123"}
            live_setup.validate(config)
            live_setup.save_env(path, config)
            self.assertEqual(live_setup.read_env(path)["AGENT_JWT_PUBLIC_KEY"], "keep-me")
            self.assertEqual(live_setup.read_env(path)["MCP_SCAN_API_KEY"], "test-secret-123")
            with self.assertRaises(ValueError):
                live_setup.validate({**config, "MCP_SCAN_BASE_URL": "http://aig-lab-model:4010/v1"})

    def test_aig_registration_creates_then_updates_one_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            config = {"MCP_SCAN_BASE_URL": "https://api.example.invalid/v1",
                      "MCP_SCAN_MODEL": "example/model", "MCP_SCAN_API_KEY": "test-secret-123"}
            live_setup.save_env(path, config)
            calls = []
            present = False

            def fake_api(method, route, payload=None):
                nonlocal present
                calls.append((method, route, payload))
                if method == "GET" and route.endswith("/models"):
                    return {"data": [{"model_id": live_setup.MODEL_ID}] if present else []}
                if method in {"POST", "PUT"}:
                    self.assertEqual(payload["model"]["token"], "test-secret-123")
                    present = True
                    return {"data": None}
                return {"data": {"model_id": live_setup.MODEL_ID,
                                 "model": {"model": config["MCP_SCAN_MODEL"],
                                           "base_url": config["MCP_SCAN_BASE_URL"]}}}

            with patch.object(live_setup, "api", side_effect=fake_api):
                live_setup.register(path)
                live_setup.register(path)
            self.assertEqual([item[0] for item in calls if item[0] in {"POST", "PUT"}],
                             ["POST", "PUT"])


if __name__ == "__main__":
    unittest.main()
