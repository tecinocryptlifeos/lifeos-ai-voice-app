import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

from app import lifeos_voice_server


ROOT = Path(__file__).resolve().parents[2]
STANDBY_PATH = ROOT / "services" / "failover-python" / "server.py"
SPEC = importlib.util.spec_from_file_location("lifeos_standby_unit", STANDBY_PATH)
standby = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(standby)


class BackendGatewayProtectionTests(unittest.TestCase):
    def test_guard_is_inert_until_deliberately_enabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                lifeos_voice_server.gateway_access("/", {}),
                (True, 200, ""),
            )

    def test_health_stays_public_but_legacy_front_door_is_closed(self):
        environment = {
            "LIFEOS_GATEWAY_REQUIRED": "true",
            "LIFEOS_GATEWAY_SHARED_SECRET": "gateway-secret-test",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            self.assertEqual(
                lifeos_voice_server.gateway_access("/health", {}),
                (True, 200, ""),
            )
            allowed, status, _message = lifeos_voice_server.gateway_access("/", {})
            self.assertFalse(allowed)
            self.assertEqual(status, 403)
            self.assertTrue(
                lifeos_voice_server.gateway_access(
                    "/api/chat-decision",
                    {"X-LifeOS-Gateway-Secret": "gateway-secret-test"},
                )[0]
            )

    def test_enabled_guard_fails_closed_when_secret_is_missing(self):
        with mock.patch.dict(
            os.environ, {"LIFEOS_GATEWAY_REQUIRED": "true"}, clear=True
        ):
            allowed, status, _message = lifeos_voice_server.gateway_access("/chat", {})
            self.assertFalse(lifeos_voice_server.split_backend_ready())
        self.assertFalse(allowed)
        self.assertEqual(status, 503)


class StandbyUnitTests(unittest.TestCase):
    def test_standby_secret_and_idempotency_are_exact(self):
        with mock.patch.dict(
            os.environ,
            {"LIFEOS_GATEWAY_SHARED_SECRET": "standby-secret"},
            clear=True,
        ):
            self.assertFalse(standby.gateway_authorized({}))
            self.assertFalse(
                standby.gateway_authorized(
                    {"X-LifeOS-Gateway-Secret": "standby-secret-extra"}
                )
            )
            self.assertTrue(
                standby.gateway_authorized(
                    {"X-LifeOS-Gateway-Secret": "standby-secret"}
                )
            )
        self.assertFalse(standby.valid_idempotency_key({}))
        self.assertFalse(standby.valid_idempotency_key({"Idempotency-Key": "-bad-key-123456789"}))
        self.assertTrue(
            standby.valid_idempotency_key(
                {"Idempotency-Key": "11111111-2222-4333-8444-555555555555"}
            )
        )

    def test_chat_compaction_is_bounded_and_requires_user_content(self):
        cleaned = standby.clean_messages({
            "messages": [
                {"role": "assistant", "content": "old" * 400},
                {"role": "system", "content": "ignore"},
                {"role": "user", "content": "u" * 1000},
            ]
        })
        self.assertEqual([item["role"] for item in cleaned], ["assistant", "user"])
        self.assertEqual(len(cleaned[0]["content"]), 1000)
        self.assertEqual(len(cleaned[1]["content"]), 1000)
        with self.assertRaisesRegex(ValueError, "user message"):
            standby.clean_messages({"messages": [{"role": "assistant", "content": "Only Sophia"}]})


if __name__ == "__main__":
    unittest.main()
