#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED_PACKAGE_ID = "losia.htc.com"
EXPECTED_HOST = "lifeosai.pages.dev"
EXPECTED_START_URL = "/"


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    manifest_path = root / "twa-manifest.json"
    assetlinks_path = root / ".well-known" / "assetlinks.json"
    template_path = root / "assetlinks.template.json"
    ignore_path = root / ".gitignore"

    for path in (manifest_path, template_path, ignore_path):
        if not path.is_file():
            fail(f"Required wrapper file is missing: {path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("packageId") != EXPECTED_PACKAGE_ID:
        fail(f"Unexpected Android package ID: {manifest.get('packageId')!r}")

    if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}", EXPECTED_PACKAGE_ID):
        fail("Android package ID format is invalid")

    if manifest.get("host") != EXPECTED_HOST:
        fail(f"Unexpected TWA host: {manifest.get('host')!r}")

    if manifest.get("startUrl") != EXPECTED_START_URL:
        fail(f"Unexpected Android start URL: {manifest.get('startUrl')!r}")

    required_values = {
        "display": "standalone",
        "orientation": "portrait",
        "fallbackType": "customtabs",
        "enableNotifications": False,
        "backgroundColor": "#000000",
        "themeColor": "#000000",
        "themeColorDark": "#000000",
        "navigationColor": "#000000",
        "navigationColorDark": "#000000",
        "navigationDividerColor": "#000000",
        "navigationDividerColorDark": "#000000",
    }

    for field, expected in required_values.items():
        if manifest.get(field) != expected:
            fail(f"Unexpected {field}: {manifest.get(field)!r}")

    version_code = manifest.get("appVersionCode")
    if not isinstance(version_code, int) or isinstance(version_code, bool) or version_code < 1:
        fail("Android version code must be a positive integer")

    signing_key = manifest.get("signingKey")
    if not isinstance(signing_key, dict):
        fail("Signing-key configuration is missing")
    if signing_key.get("path") != "./signing-key.jks":
        fail("Unexpected signing-key path")
    if signing_key.get("alias") != "losai-upload":
        fail("Unexpected signing-key alias")

    expected_origin = f"https://{EXPECTED_HOST}"
    for field in ("iconUrl", "maskableIconUrl", "webManifestUrl"):
        value = manifest.get(field)
        if not isinstance(value, str):
            fail(f"{field} is missing")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != EXPECTED_HOST
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            fail(f"{field} must use the trusted HTTPS host")
        if not value.startswith(expected_origin + "/"):
            fail(f"{field} must use the production Pages origin")

    template = json.loads(template_path.read_text(encoding="utf-8"))
    try:
        target = template[0]["target"]
        fingerprints = target["sha256_cert_fingerprints"]
    except (IndexError, KeyError, TypeError) as error:
        fail(f"Asset Links template has an invalid structure: {error}")

    if target.get("package_name") != EXPECTED_PACKAGE_ID:
        fail("Asset Links package ID does not match the Android wrapper")
    if fingerprints != ["__SHA256_CERT_FINGERPRINT__"]:
        fail("Asset Links template must retain exactly one fingerprint placeholder")

    if assetlinks_path.is_file():
        assetlinks = json.loads(assetlinks_path.read_text(encoding="utf-8"))
        try:
            live_target = assetlinks[0]["target"]
        except (IndexError, KeyError, TypeError) as error:
            fail(f"Live Asset Links has an invalid structure: {error}")
        if live_target.get("package_name") != EXPECTED_PACKAGE_ID:
            fail("Live Asset Links package ID does not match the Android wrapper")
        live_fingerprints = live_target.get("sha256_cert_fingerprints")
        if not isinstance(live_fingerprints, list) or len(live_fingerprints) != 1:
            fail("Live Asset Links must contain exactly one signing fingerprint")

    ignore_text = ignore_path.read_text(encoding="utf-8")
    for required_rule in ("*.jks", "*.keystore", "signing-key.jks", "*.apk", "*.aab"):
        if required_rule not in ignore_text:
            fail(f"Missing security ignore rule: {required_rule}")

    forbidden_extensions = {".jks", ".keystore", ".apk", ".aab", ".apks"}
    forbidden_files = [
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden_extensions
    ]
    if forbidden_files:
        fail(
            "Signing or build artifacts must not exist during validation:\n- "
            + "\n- ".join(str(path.relative_to(root)) for path in forbidden_files)
        )

    forbidden_secret_fragments = (
        "sb_" + "secret_",
        "sk-" + "proj-",
        "AIza" + "Sy",
        "SUPABASE_" + "SECRET_KEY=",
        "GEMINI_" + "API_KEY=",
    )
    leaked = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() in forbidden_extensions:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for fragment in forbidden_secret_fragments:
            if fragment in text:
                leaked.add(fragment)
    if leaked:
        fail("Potential secret material detected: " + ", ".join(sorted(leaked)))

    print("PACKAGE_ID=PASS")
    print("TRUSTED_HOST=PASS")
    print("START_ROUTE=PASS")
    print("PAGES_ORIGIN=PASS")
    print("BUBBLEWRAP_FIELDS=PASS")
    print("CUSTOM_TABS_FALLBACK=PASS")
    print("SIGNING_KEY_EXCLUDED=PASS")
    print("ASSETLINKS_TEMPLATE=PASS")
    print("SECRET_SCAN=PASS")
    print("TWA_WRAPPER_CONFIGURATION=PASS")


if __name__ == "__main__":
    main()
