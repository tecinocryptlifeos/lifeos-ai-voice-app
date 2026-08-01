import importlib.util
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "services" / "failover-python" / "server.py"
SPEC = importlib.util.spec_from_file_location("lifeos_standby_http", PATH)
standby = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(standby)


class StandbyHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), standby.StandbyHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, path, method="GET", headers=None, body=None):
        request = urllib.request.Request(
            self.origin + path,
            method=method,
            headers=headers or {},
            data=None if body is None else json.dumps(body).encode("utf-8"),
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_health_is_public_and_reports_only_slim_capabilities(self):
        with mock.patch.dict(
            os.environ,
            {
                "LIFEOS_GATEWAY_SHARED_SECRET": "standby-secret",
                "GEMINI_API_KEY": "gemini-test",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "publishable-test",
                "SUPABASE_SECRET_KEY": "secret-test",
            },
            clear=True,
        ):
            status, data = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["role"], "warm-standby")
        self.assertFalse(data["static_site"])
        self.assertFalse(data["admin"])
        self.assertFalse(data["email_worker"])

    def test_health_fails_when_required_runtime_configuration_is_absent(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            status, data = self.request("/health")
        self.assertEqual(status, 503)
        self.assertFalse(data["ok"])

    def test_application_routes_require_gateway_secret(self):
        with mock.patch.dict(
            os.environ,
            {"LIFEOS_GATEWAY_SHARED_SECRET": "standby-secret"},
            clear=True,
        ):
            status, data = self.request("/api/config")
            self.assertEqual(status, 403)
            self.assertEqual(data["code"], "GATEWAY_REQUIRED")
            status, data = self.request(
                "/api/config",
                headers={"X-LifeOS-Gateway-Secret": "standby-secret"},
            )
            self.assertEqual(status, 200)
            self.assertFalse(data["configured"])

    def test_mutation_rejects_missing_idempotency_before_auth_or_upstream_work(self):
        with mock.patch.dict(
            os.environ,
            {"LIFEOS_GATEWAY_SHARED_SECRET": "standby-secret"},
            clear=True,
        ):
            status, data = self.request(
                "/api/chat-decision",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-LifeOS-Gateway-Secret": "standby-secret",
                },
                body={"messages": [{"role": "user", "content": "hello"}]},
            )
        self.assertEqual(status, 400)
        self.assertEqual(data["code"], "IDEMPOTENCY_KEY_REQUIRED")


if __name__ == "__main__":
    unittest.main()
