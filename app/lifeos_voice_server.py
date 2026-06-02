import os
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    from lifeos_public_tts import generate_lifeos_voice_wav
except ImportError:
    from app.lifeos_public_tts import generate_lifeos_voice_wav

try:
    from gemini_client import GeminiClient
except ImportError:
    from app.gemini_client import GeminiClient


BASE_DIR = Path(__file__).resolve().parents[1]
WEB_FILE = BASE_DIR / "web" / "lifeos_voice" / "index.html"
AUDIO_DIR = BASE_DIR / "web" / "lifeos_voice" / "audio"

HOST = os.environ.get("LIFEOS_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT") or os.environ.get("LIFEOS_PORT") or "8787")


SYSTEM_STYLE = """
You are LifeOS AI, a premium decision-audit assistant.
Give a concise, direct answer using this structure:

Verdict:
Reality Check:
Main Risk:
Better Move:
Next Action:
Final Truth:

Keep the answer sharp, practical, and useful.
"""


class LifeOSVoiceHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send(self, status, body, content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, b"OK", "text/plain; charset=utf-8")
            return

        if self.path in ("/", "/index.html"):
            if not WEB_FILE.exists():
                self._send(500, b"index.html missing")
                return

            self._send(200, WEB_FILE.read_bytes(), "text/html; charset=utf-8")
            return

        if self.path.startswith("/audio/") and self.path.endswith(".wav"):
            name = self.path.split("/")[-1]
            audio_file = AUDIO_DIR / name

            if audio_file.exists() and audio_file.is_file():
                self._send(200, audio_file.read_bytes(), "audio/wav")
                return

            self._send(404, b"Audio not found")
            return

        self._send(404, b"Not found")

    def do_POST(self):
        if self.path != "/api/text-audit":
            self._send(404, b"Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))

            user_text = (data.get("text") or "").strip()

            if not user_text:
                raise ValueError("Text is required")

            client = GeminiClient()

            prompt = f"{SYSTEM_STYLE}\n\nUser decision:\n{user_text}"

            reply = client.generate_text(
                prompt,
                timeout=75,
                retries=3,
            )

            voice_prompt = (
                "Rewrite this audit as a natural spoken reply for Sophia, the LifeOS AI premium voice. "
                "Use calm London English wording, smooth rhythm, and human advisor tone. "
                "Do not read labels like Verdict, Main Risk, Better Move, Next Action, or Final Truth. "
                "Do not sound robotic, dramatic, childish, rushed, or overly formal. "
                "Speak directly to the user in 45 to 65 words. "
                "Use natural pauses, emotional intelligence, and premium clarity. "
                "Audit to convert into speech:\n\n"
                + reply
            )

            voice = client.generate_text(
                voice_prompt,
                timeout=60,
                retries=2,
            )

            audio_name = f"lifeos_voice_{int(__import__('time').time())}.wav"
            audio_path = AUDIO_DIR / audio_name
            generate_lifeos_voice_wav(voice, audio_path)

            payload = {
                "ok": True,
                "reply": voice,
                "voice": voice,
                "audio_url": f"/audio/{audio_name}",
            }

            self._send(
                200,
                json.dumps(payload).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        except Exception as e:
            payload = {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
            }

            self._send(
                500,
                json.dumps(payload).encode("utf-8"),
                "application/json; charset=utf-8",
            )


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY is missing. Run: source ~/.truthlayer_env")
        raise SystemExit(1)

    print(f"✅ LifeOS AI Voice server running at http://{HOST}:{PORT}")
    print("Open that address in your Android browser.")
    HTTPServer((HOST, PORT), LifeOSVoiceHandler).serve_forever()


if __name__ == "__main__":
    main()
