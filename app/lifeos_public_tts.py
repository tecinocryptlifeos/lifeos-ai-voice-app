import os
import json
import wave
import base64
import urllib.request
import urllib.error
from pathlib import Path


TTS_MODEL = os.environ.get("LIFEOS_TTS_MODEL", "gemini-3.1-flash-tts-preview")
TTS_VOICE = os.environ.get("LIFEOS_TTS_VOICE", "Despina")


def write_wav(path, pcm_data, channels=1, rate=24000, sample_width=2):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)


def build_voice_prompt(text):
    clean = " ".join(str(text or "").replace("*", "").split())

    return (
        "Read the following text exactly as written. "
        "Do not add words. Do not remove words. Do not summarize. Do not rephrase. "
        "Use Sophia's premium LifeOS AI voice: calm London English lady delivery, smooth, warm, clear, and composed. "
        "Use natural pauses and premium advisor tone, but keep the wording exactly the same. "
        "Text to read: "
        + clean
    )

def generate_lifeos_voice_wav(text, output_path, voice_name=None, timeout=90):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")

    voice = voice_name or TTS_VOICE
    prompt = build_voice_prompt(text)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice
                    }
                }
            }
        },
        "model": TTS_MODEL
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini TTS HTTP {e.code}: {body[:1000]}")

    part = result["candidates"][0]["content"]["parts"][0]
    inline = part.get("inlineData") or part.get("inline_data")

    if not inline or not inline.get("data"):
        raise RuntimeError("Gemini TTS did not return inline audio data")

    pcm_data = base64.b64decode(inline["data"])
    write_wav(output_path, pcm_data)

    return str(output_path)
