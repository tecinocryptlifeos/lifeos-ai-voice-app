import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PagesBuildTests(unittest.TestCase):
    def run_build(self, output, **overrides):
        environment = os.environ.copy()
        for key in (
            "LIFEOS_GA_MEASUREMENT_ID",
            "LIFEOS_ADSENSE_PUBLISHER_ID",
        ):
            environment.pop(key, None)
        environment.update({
            "LIFEOS_PUBLIC_SITE_ORIGIN": "https://losai.ng.eu.org",
            "LIFEOS_API_ORIGIN": "https://api.losai.ng.eu.org",
            "LIFEOS_PAGES_PREVIEW": "true",
            **overrides,
        })
        return subprocess.run(
            [sys.executable, "apps/web/build.py", "--output", str(output)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_preview_build_has_clean_routes_gateway_origin_and_no_legacy_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pages"
            result = self.run_build(output)
            self.assertIn("PAGES_BUILD=PASS", result.stdout)
            for route in ("chat", "voice", "account", "admin"):
                page = (output / route / "index.html").read_text(encoding="utf-8")
                self.assertIn('name="lifeos-api-origin" content="https://api.losai.ng.eu.org"', page)
                self.assertNotIn("https://losai.onrender.com", page)
                self.assertNotIn("google-adsense-account", page)
            self.assertIn("Disallow: /", (output / "robots.txt").read_text(encoding="utf-8"))
            self.assertIn("X-Robots-Tag: noindex", (output / "_headers").read_text(encoding="utf-8"))
            self.assertFalse((output / "ads.txt").exists())

    def test_valid_monetization_is_public_content_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pages"
            self.run_build(
                output,
                LIFEOS_PAGES_PREVIEW="false",
                LIFEOS_GA_MEASUREMENT_ID="G-ABCD1234",
                LIFEOS_ADSENSE_PUBLISHER_ID="pub-1234567890123456",
            )
            home = (output / "index.html").read_text(encoding="utf-8")
            chat = (output / "chat" / "index.html").read_text(encoding="utf-8")
            self.assertIn("G-ABCD1234", home)
            self.assertIn("ca-pub-1234567890123456", home)
            self.assertNotIn("G-ABCD1234", chat)
            self.assertNotIn("ca-pub-1234567890123456", chat)
            self.assertEqual(
                (output / "ads.txt").read_text(encoding="utf-8"),
                "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n",
            )


if __name__ == "__main__":
    unittest.main()
