import os
import json
import time
import urllib.request
import urllib.error


DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"


class GeminiClient:
    """
    Safe Gemini client for TruthLayer.

    This file is separate from app/bot.py.
    It will not change current bot behavior until bot.py is manually connected to it.
    """

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL

        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is missing.")

        if not self.model:
            raise RuntimeError("Gemini model is missing.")

    def build_url(self, model=None):
        use_model = model or self.model
        return (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{use_model}:generateContent"
            f"?key={self.api_key}"
        )

    def generate(self, payload, timeout=75, retries=3, label="Gemini request", model=None):
        """
        Send one Gemini generateContent request with controlled retry behavior.
        """

        if not isinstance(payload, dict):
            raise TypeError("Gemini payload must be a dictionary.")

        url = self.build_url(model=model)
        data = json.dumps(payload).encode("utf-8")

        last_error = None

        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {e.code}: {body[:800]}"

                # Retry only rate-limit/server failures.
                # Do not blindly retry bad request or authentication mistakes.
                if e.code not in (429, 500, 502, 503, 504):
                    break

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"

            if attempt < retries:
                time.sleep(min(2 * attempt, 6))

        raise RuntimeError(f"{label} failed after {retries} attempt(s). Last error: {last_error}")

    def extract_text(self, result, fallback=""):
        """
        Safely extract text from a Gemini response.
        """

        try:
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            return fallback

    def generate_text(self, text, timeout=75, retries=3):
        """
        Convenience method for simple text-only Gemini calls.
        """

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": text}
                    ]
                }
            ]
        }

        result = self.generate(
            payload,
            timeout=timeout,
            retries=retries,
            label="Gemini text request",
        )

        return self.extract_text(result)
