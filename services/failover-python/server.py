#!/usr/bin/env python3
"""Slim LOSAI Python standby for Northflank.

This service intentionally has no static site, admin, queue, email, analytics,
or media routes. Cloudflare is its only application caller.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.gemini_client import GeminiClient  # noqa: E402
from app.gemini_live_gateway import (  # noqa: E402
    GeminiLiveRateLimit,
    create_gemini_live_token,
    gemini_live_status,
)
from app.lifeos_auth_analytics import (  # noqa: E402
    account_profile,
    public_config,
    verify_user,
)


RELEASE = "losai-northflank-standby-v1"
HOST = os.environ.get("LIFEOS_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT") or os.environ.get("LIFEOS_PORT") or "8080")


def gateway_authorized(headers) -> bool:
    expected = os.environ.get("LIFEOS_GATEWAY_SHARED_SECRET", "").strip()
    supplied = str(headers.get("X-LifeOS-Gateway-Secret") or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def standby_ready() -> bool:
    return all((
        os.environ.get("LIFEOS_GATEWAY_SHARED_SECRET", "").strip(),
        os.environ.get("GEMINI_API_KEY", "").strip(),
        os.environ.get("SUPABASE_URL", "").strip(),
        (
            os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
            or os.environ.get("SUPABASE_ANON_KEY", "").strip()
        ),
        (
            os.environ.get("SUPABASE_SECRET_KEY", "").strip()
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        ),
    ))


def valid_idempotency_key(headers) -> bool:
    value = str(headers.get("Idempotency-Key") or "").strip()
    return bool(value[:1].isalnum()) and 16 <= len(value) <= 200 and all(
        character.isalnum() or character in "._:-" for character in value
    )


def clean_messages(payload):
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        raise ValueError("Messages must be a list")
    cleaned = []
    excluded = (
        "could not complete the continuation",
        "under high demand",
        "reviewing the decision thread",
    )
    for item in messages[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        if any(fragment in content.lower() for fragment in excluded):
            continue
        cleaned.append((role, content[: 900 if role == "user" else 700]))
    if not cleaned or not any(role == "user" for role, _ in cleaned):
        raise ValueError("A user message is required")
    return cleaned


def chat_prompt(payload) -> str:
    cleaned = clean_messages(payload)
    latest_user = next(content for role, content in reversed(cleaned) if role == "user")
    conversation = "\n".join(f"{role.upper()}: {content}" for role, content in cleaned)
    return f"""
You are Sophia, the LifeOS AI decision-intelligence assistant. Continue the
conversation and answer the exact request in the user's current language.

Latest user message:
{latest_user}

Compact conversation context:
{conversation}

Use Google Search when the answer depends on current facts. Separate verified
facts from inference and uncertainty. For decisions, explain likely short- and
long-term outcomes, the main risk, opportunity cost, safer alternative, and one
practical next action. Never guarantee a future, profit, price, medical result,
or legal result. Protect privacy. Use plain readable text, normally 90 to 220
words, and finish the final sentence.
""".strip()


class StandbyHandler(BaseHTTPRequestHandler):
    server_version = "LifeOSStandby/1"

    def log_message(self, format, *args):
        return

    def path_only(self):
        return unquote(self.path.split("?", 1)[0]).rstrip("/") or "/"

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("X-LifeOS-Standby-Release", RELEASE)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def require_gateway(self):
        if gateway_authorized(self.headers):
            return True
        self.send_json(403, {
            "ok": False,
            "code": "GATEWAY_REQUIRED",
            "error": "The Cloudflare API gateway is required.",
        })
        return False

    def require_user(self, profile_required=True):
        try:
            user, token = verify_user(self.headers)
            profile = account_profile(user, token)
            if profile_required and not profile.get("complete"):
                raise PermissionError("Complete your LifeOS profile before using Sophia")
            return user, token, profile
        except PermissionError as error:
            code = "PROFILE_REQUIRED" if "Complete your LifeOS profile" in str(error) else "AUTH_REQUIRED"
            self.send_json(403 if code == "PROFILE_REQUIRED" else 401, {
                "ok": False, "code": code, "error": str(error),
            })
        except RuntimeError as error:
            self.send_json(503, {"ok": False, "error": str(error)[:500]})
        except Exception:
            self.send_json(503, {"ok": False, "error": "The authentication service is unavailable"})
        return None

    def read_json(self, maximum=60000):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid Content-Length") from error
        if length < 1 or length > maximum:
            raise ValueError("Invalid request body size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("The request body must be an object")
        return payload

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path_only()
        if path == "/health":
            ready = standby_ready()
            self.send_json(200 if ready else 503, {
                "ok": ready,
                "role": "warm-standby",
                "release": RELEASE,
                "static_site": False,
                "admin": False,
                "analytics_worker": False,
                "email_worker": False,
            })
            return
        if not self.require_gateway():
            return
        if path in {"/api/config", "/api/auth-config"}:
            self.send_json(200, public_config())
            return
        if path == "/api/gemini-live-status":
            self.send_json(200, gemini_live_status())
            return
        if path in {"/api/session", "/api/session-status"}:
            result = self.require_user(profile_required=False)
            if result:
                user, _token, profile = result
                self.send_json(200, {
                    "ok": True,
                    "user_id": user.get("id"),
                    "profile_complete": bool(profile.get("complete")),
                })
            return
        if path == "/api/account-profile":
            result = self.require_user(profile_required=False)
            if result:
                self.send_json(200, result[2])
            return
        self.send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        path = self.path_only()
        if not self.require_gateway():
            return
        if not valid_idempotency_key(self.headers):
            self.send_json(400, {
                "ok": False,
                "code": "IDEMPOTENCY_KEY_REQUIRED",
                "error": "A valid Idempotency-Key is required for this mutation.",
            })
            return
        result = self.require_user(profile_required=True)
        if not result:
            return
        user, _token, _profile = result
        if path == "/api/gemini-live-token":
            try:
                payload = self.read_json(maximum=4096) if int(self.headers.get("Content-Length", "0")) else {}
                preference = str(payload.get("model_preference") or "primary")[:20]
                response = create_gemini_live_token(f"user:{user.get('id')}", preference)
                self.send_json(200, response)
            except GeminiLiveRateLimit as error:
                self.send_json(429, {"ok": False, "error": str(error), "retry_after": error.retry_after})
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json(400, {"ok": False, "error": str(error)[:500]})
            except Exception as error:
                self.send_json(502, {"ok": False, "error": f"{type(error).__name__}: {error}"[:500]})
            return
        if path == "/api/chat-decision":
            try:
                payload = self.read_json()
                generated = GeminiClient().generate_grounded_text(
                    chat_prompt(payload), timeout=18, retries=1, max_output_tokens=900
                )
                sources = generated.get("sources") or []
                self.send_json(200, {
                    "ok": True,
                    "reply": str(generated.get("text") or "").strip(),
                    "sources": sources,
                    "grounded": bool(sources),
                    "audio_url": None,
                    "tts_error": None,
                })
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json(400, {"ok": False, "error": str(error)[:500]})
            except Exception:
                self.send_json(503, {
                    "ok": False,
                    "code": "STANDBY_INTELLIGENCE_UNAVAILABLE",
                    "error": "The standby intelligence service is temporarily unavailable.",
                })
            return
        self.send_json(404, {"ok": False, "error": "Not found"})


def main():
    with ThreadingHTTPServer((HOST, PORT), StandbyHandler) as server:
        print(f"LifeOS warm standby listening on http://{HOST}:{PORT}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
