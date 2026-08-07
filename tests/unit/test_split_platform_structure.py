import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SplitPlatformStructureTests(unittest.TestCase):
    def test_approved_directory_contract_exists(self):
        required = (
            "apps/web/homepage", "apps/web/chat", "apps/web/voice",
            "apps/web/account", "apps/web/admin", "apps/web/public",
            "services/render-python", "services/failover-python",
            "services/edge-gateway", "infrastructure/render",
            "infrastructure/cloudflare", "infrastructure/northflank",
            "infrastructure/supabase", "operations/termux",
            "operations/backup", "operations/restore",
            "operations/health-check", "operations/failover", "tests/unit",
            "tests/integration", "tests/failover", "tests/capacity",
            "docs/architecture", "docs/deployment", "docs/disaster-recovery",
            "docs/environment-variable-register",
        )
        missing = [item for item in required if not (ROOT / item).is_dir()]
        self.assertEqual(missing, [])

    def test_private_pages_load_gateway_adapter_before_account_runtime(self):
        pages = (
            ROOT / "web/lifeos_voice/chat.html",
            ROOT / "web/lifeos_voice/gemini_live.html",
            ROOT / "web/lifeos_voice/admin.html",
            ROOT / "web/lifeos_voice/reset_password.html",
            ROOT / "apps/web/account/index.html",
        )
        for path in pages:
            markup = path.read_text(encoding="utf-8")
            with self.subTest(page=path.name):
                self.assertIn("lifeos_api_gateway_v1.js", markup)
                self.assertLess(
                    markup.index("lifeos_api_gateway_v1.js"),
                    markup.index("lifeos_account_v1.js"),
                )

    def test_homepage_uses_links_and_does_not_open_a_websocket(self):
        homepage = (ROOT / "web/lifeos_voice/index.html").read_text(encoding="utf-8")
        self.assertIn('href="/chat"', homepage)
        self.assertIn('href="/voice"', homepage)
        self.assertNotIn("new WebSocket", homepage)
        self.assertNotIn("wss://", homepage)

    def test_five_minute_cron_and_nonautomatic_render_deploy_are_explicit(self):
        wrangler = (
            ROOT / "infrastructure/cloudflare/wrangler.toml.template"
        ).read_text(encoding="utf-8")
        render = (
            ROOT / "infrastructure/render/render.split-platform.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn('crons = ["*/5 * * * *"]', wrangler)
        self.assertIn("autoDeployTrigger: off", render)
        self.assertIn("LIFEOS_GATEWAY_REQUIRED", render)

    def test_account_and_api_are_disallowed_from_public_indexing(self):
        robots = (ROOT / "web/lifeos_voice/robots.txt").read_text(encoding="utf-8")
        self.assertIn("Disallow: /account", robots)
        self.assertIn("Disallow: /api/", robots)


if __name__ == "__main__":
    unittest.main()
