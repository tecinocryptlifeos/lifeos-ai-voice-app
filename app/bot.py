import os
import json
import time
import uuid
import urllib.request
import urllib.parse
import base64
import subprocess
from datetime import datetime, timezone

try:
    from gemini_client import GeminiClient
except ImportError:
    from app.gemini_client import GeminiClient


BASE_DIR = os.path.expanduser("~/truthlayer-ai")
ENV_FILE = os.path.expanduser("~/.truthlayer_env")
PROMPT_FILE = os.path.join(BASE_DIR, "prompts", "truth_engine_prompt_v1.txt")
DATA_FILE = os.path.join(BASE_DIR, "data", "audit_history.jsonl")
FEEDBACK_FILE = os.path.join(BASE_DIR, "data", "audit_feedback.jsonl")
PROFILE_FILE = os.path.join(BASE_DIR, "data", "user_profiles.json")
TRUST_FILE = os.path.join(BASE_DIR, "credibility", "trust_rules_v1.txt")
FORMAT_FILE = os.path.join(BASE_DIR, "credibility", "premium_audit_format_v2.txt")
VOICE_DIR = os.path.join(BASE_DIR, "data", "voice_notes")
VOICE_REPLY_DIR = os.path.join(BASE_DIR, "data", "voice_replies")

GEMINI_MODEL = "gemini-3-flash-preview"
TTS_MODEL = "gemini-3.1-flash-tts-preview"


def load_env_file(path):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line.replace("export ", "", 1)

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')

            if key and value:
                os.environ[key] = value


def read_truth_prompt():
    if not os.path.exists(PROMPT_FILE):
        return "You are LifeOS AI. Audit decisions using verdict, risk, hidden cost, and next best action."

    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        prompt = f.read()

    prompt = prompt.replace("TruthLayer AI", "LifeOS AI")
    return prompt


def read_trust_rules():
    if not os.path.exists(TRUST_FILE):
        return "LifeOS AI must be honest, careful with risk, and avoid pretending certainty."

    with open(TRUST_FILE, "r", encoding="utf-8") as f:
        return f.read()


def read_premium_format():
    if not os.path.exists(FORMAT_FILE):
        return "Use a premium structured decision audit format with verdict, score, risk, evidence gap, red flag, better move, and next action."

    with open(FORMAT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def request_with_retry(req, timeout=60, retries=3, label="network"):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        except Exception as e:
            last_error = e
            print(f"{label} error attempt {attempt}/{retries}: {e}")

            if attempt < retries:
                wait_time = attempt * 4
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)

    raise RuntimeError(f"{label} failed after {retries} attempts. Last error: {last_error}")


def telegram_api(method, payload=None, timeout=30):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")

    url = f"https://api.telegram.org/bot{token}/{method}"

    if payload is None:
        payload = {}

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")

    return request_with_retry(req, timeout=timeout, retries=3, label="Telegram connection")


def send_message(chat_id, text):
    max_length = 3900

    if len(text) <= max_length:
        telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": text
        })
        return

    parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]

    for part in parts:
        telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": part
        })
        time.sleep(0.5)


def create_audit_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short_id = uuid.uuid4().hex[:6].upper()
    return f"LOS-{stamp}-{short_id}"


def save_audit(record):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_recent_audits(chat_id, limit=5):
    if not os.path.exists(DATA_FILE):
        return []

    records = []

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in reversed(lines):
        line = line.strip()

        if not line:
            continue

        try:
            record = json.loads(line)
        except Exception:
            continue

        if str(record.get("chat_id")) == str(chat_id):
            records.append(record)

        if len(records) >= limit:
            break

    return records


def format_history(records):
    if not records:
        return "No saved decision audits yet."

    output = "LIFEOS AI AUDIT HISTORY\n\n"

    for record in records:
        output += f"Audit ID: {record.get('audit_id')}\n"
        output += f"Time: {record.get('timestamp_utc')}\n"
        output += f"Decision: {record.get('user_text')[:120]}\n"
        output += "-----\n"

    return output.strip()


def find_audit_by_id(chat_id, audit_id):
    if not os.path.exists(DATA_FILE):
        return None

    target_id = audit_id.strip().upper()

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in reversed(lines):
        line = line.strip()

        if not line:
            continue

        try:
            record = json.loads(line)
        except Exception:
            continue

        if str(record.get("chat_id")) == str(chat_id) and str(record.get("audit_id")).upper() == target_id:
            return record

    return None


def format_saved_audit(record):
    return (
        "SAVED LIFEOS AI AUDIT\n\n"
        f"Audit ID: {record.get('audit_id')}\n"
        f"Time: {record.get('timestamp_utc')}\n\n"
        f"Original Decision:\n{record.get('user_text')}\n\n"
        f"Audit Report:\n{record.get('audit')}"
    )


def save_feedback(record):
    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)

    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_recent_feedback(chat_id, limit=10):
    if not os.path.exists(FEEDBACK_FILE):
        return []

    records = []

    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in reversed(lines):
        line = line.strip()

        if not line:
            continue

        try:
            record = json.loads(line)
        except Exception:
            continue

        if str(record.get("chat_id")) == str(chat_id):
            records.append(record)

        if len(records) >= limit:
            break

    return records


def format_feedback(records):
    if not records:
        return "No audit feedback saved yet."

    ratings = [int(r.get("rating", 0)) for r in records if r.get("rating")]
    average = sum(ratings) / len(ratings) if ratings else 0

    output = "LIFEOS AI FEEDBACK REVIEW\n\n"
    output += f"Recent ratings: {len(records)}\n"
    output += f"Average rating: {average:.1f}/5\n\n"

    for record in records:
        output += f"Audit ID: {record.get('audit_id')}\n"
        output += f"Rating: {record.get('rating')}/5\n"
        output += f"Time: {record.get('timestamp_utc')}\n"

        note = record.get("note")
        if note:
            output += f"Note: {note}\n"

        output += "-----\n"

    return output.strip()


def load_profiles():
    if not os.path.exists(PROFILE_FILE):
        return {}

    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return {}

        return json.loads(content)

    except Exception:
        return {}


def save_profiles(profiles):
    os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)

    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


def get_profile_key(chat_id):
    return str(chat_id)


def get_profile(chat_id):
    profiles = load_profiles()
    key = get_profile_key(chat_id)

    default_profile = {
        "main_goal": "",
        "current_project": "",
        "priority_focus": "",
        "risk_level": "",
        "repeated_mistake": "",
        "updated_at_utc": ""
    }

    return profiles.get(key, default_profile)


def update_profile(chat_id, field, value):
    profiles = load_profiles()
    key = get_profile_key(chat_id)

    profile = get_profile(chat_id)
    profile[field] = value.strip()
    profile["updated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    profiles[key] = profile
    save_profiles(profiles)

    return profile


def clear_profile(chat_id):
    profiles = load_profiles()
    key = get_profile_key(chat_id)

    if key in profiles:
        del profiles[key]

    save_profiles(profiles)


def format_profile(profile):
    if not any([
        profile.get("main_goal"),
        profile.get("current_project"),
        profile.get("priority_focus"),
        profile.get("risk_level"),
        profile.get("repeated_mistake")
    ]):
        return (
            "LIFEOS AI PROFILE\n\n"
            "No profile memory saved yet.\n\n"
            "Set your profile with:\n"
            "/setgoal Your main goal\n"
            "/setproject Your current project\n"
            "/setfocus Your priority focus\n"
            "/setrisk Low, Medium, or High\n"
            "/setmistake Your repeated mistake"
        )

    return (
        "LIFEOS AI PROFILE\n\n"
        f"Main Goal: {profile.get('main_goal') or 'Not set'}\n"
        f"Current Project: {profile.get('current_project') or 'Not set'}\n"
        f"Priority Focus: {profile.get('priority_focus') or 'Not set'}\n"
        f"Risk Level: {profile.get('risk_level') or 'Not set'}\n"
        f"Repeated Mistake: {profile.get('repeated_mistake') or 'Not set'}\n"
        f"Updated: {profile.get('updated_at_utc') or 'Not set'}"
    )


def profile_context_for_prompt(profile):
    return f"""
Saved LifeOS user profile:
Main Goal: {profile.get('main_goal') or 'Not provided'}
Current Project: {profile.get('current_project') or 'Not provided'}
Priority Focus: {profile.get('priority_focus') or 'Not provided'}
Risk Level: {profile.get('risk_level') or 'Not provided'}
Repeated Mistake: {profile.get('repeated_mistake') or 'Not provided'}

Use this profile only to improve decision relevance.
Do not invent missing facts.
If profile information is missing, judge the decision using the available context.
"""


def command_value(text, command):
    value = text[len(command):].strip()

    if not value:
        return ""

    return value


def is_admin_user(chat_id, from_user):
    admin_id = os.environ.get("ADMIN_USER_ID", "").strip()

    if not admin_id:
        return False

    user_id = str(from_user.get("id", ""))
    chat_id_text = str(chat_id)

    return admin_id in [user_id, chat_id_text]


def load_all_feedback(limit=20):
    if not os.path.exists(FEEDBACK_FILE):
        return []

    records = []

    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in reversed(lines):
        line = line.strip()

        if not line:
            continue

        try:
            record = json.loads(line)
        except Exception:
            continue

        records.append(record)

        if len(records) >= limit:
            break

    return records


def format_owner_feedback(records):
    if not records:
        return "No audit feedback saved yet."

    ratings = [int(r.get("rating", 0)) for r in records if r.get("rating")]
    average = sum(ratings) / len(ratings) if ratings else 0

    output = "LIFEOS AI OWNER FEEDBACK REVIEW\n\n"
    output += f"Total recent ratings: {len(records)}\n"
    output += f"Average rating: {average:.1f}/5\n\n"

    for record in records:
        output += f"Audit ID: {record.get('audit_id')}\n"
        output += f"Rating: {record.get('rating')}/5\n"
        output += f"Time: {record.get('timestamp_utc')}\n"
        output += f"User ID: {record.get('user_id')}\n"

        username = record.get("username")
        if username:
            output += f"Username: @{username}\n"

        note = record.get("note")
        if note:
            output += f"Note: {note}\n"

        output += "-----\n"

    return output.strip()



def telegram_get_file(file_id):
    result = telegram_api("getFile", {"file_id": file_id}, timeout=30)

    if not result.get("ok"):
        raise RuntimeError("Telegram getFile failed.")

    file_path = result.get("result", {}).get("file_path")

    if not file_path:
        raise RuntimeError("Telegram did not return file_path.")

    return file_path


def download_telegram_file(file_path, local_path):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")

    url = f"https://api.telegram.org/file/bot{token}/{file_path}"

    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()

    with open(local_path, "wb") as f:
        f.write(data)

    return local_path


def gemini_transcribe_audio(audio_path, mime_type="audio/ogg"):
    key = os.environ.get("GEMINI_API_KEY")

    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Transcribe this Telegram voice note accurately. "
                            "Return only the spoken words. "
                            "Do not add explanation, formatting, or commentary."
                        )
                    },
                    {
                        "inline_data": {
                            "mime_type": mime_type or "audio/ogg",
                            "data": audio_b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.7,
            "maxOutputTokens": 700
        }
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key
        },
        method="POST"
    )

    client = GeminiClient(api_key=key, model=GEMINI_MODEL)
    result = client.generate(payload, timeout=90, retries=4, label="Gemini voice transcription")

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ""


def handle_voice_message(message):
    chat = message.get("chat", {})
    from_user = message.get("from", {})
    voice = message.get("voice", {})

    chat_id = chat.get("id")
    file_id = voice.get("file_id")
    mime_type = voice.get("mime_type") or "audio/ogg"

    if not chat_id or not file_id:
        return

    send_message(chat_id, "Voice note received. Transcribing your decision now...")

    try:
        os.makedirs(VOICE_DIR, exist_ok=True)

        file_path = telegram_get_file(file_id)
        ext = os.path.splitext(file_path)[1] or ".oga"
        local_path = os.path.join(VOICE_DIR, f"{chat_id}_{int(time.time())}{ext}")

        download_telegram_file(file_path, local_path)

        transcript = gemini_transcribe_audio(local_path, mime_type=mime_type)

        if not transcript:
            send_message(chat_id, "I received the voice note, but I could not transcribe it clearly. Please try again with a clearer voice note.")
            return

        send_message(chat_id, "Transcribed decision:\n" + transcript + "\n\nAuditing now...")

        audit_id = create_audit_id()
        timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        profile = get_profile(chat_id)

        audit = gemini_audit(transcript, profile)

        premium_response = (
            f"Audit ID: {audit_id}\n"
            f"Timestamp: {timestamp_utc}\n"
            f"Source: Voice note\n\n"
            f"Transcript:\n{transcript}\n\n"
            f"{audit}"
        )

        record = {
            "audit_id": audit_id,
            "timestamp_utc": timestamp_utc,
            "chat_id": chat_id,
            "user_id": from_user.get("id"),
            "username": from_user.get("username"),
            "first_name": from_user.get("first_name"),
            "source": "voice",
            "user_text": transcript,
            "profile_snapshot": profile,
            "audit": audit
        }

        save_audit(record)
        send_message(chat_id, premium_response)
        send_message(chat_id, "Generating voice summary...")
        send_audit_voice_summary(chat_id, audit_id, audit)

    except Exception as e:
        send_message(
            chat_id,
            "LifeOS AI hit a voice-processing error after retrying.\n\n"
            "The bot is still running.\n\n"
            "Error:\n" + str(e)
        )



def clean_voice_text(text):
    cleaned = (
        text.replace("**", "")
        .replace("*", "")
        .replace("__", "")
        .replace("_", "")
        .replace("#", "")
        .strip()
    )
    cleaned = " ".join(cleaned.split())
    return cleaned


def shorten_voice_part(text, max_words=26):
    text = clean_voice_text(text)
    words = text.split()

    if len(words) <= max_words:
        return text

    return " ".join(words[:max_words]).rstrip(",;:") + "."


def extract_audit_section(audit, section_name):
    lines = audit.splitlines()

    known_sections = [
        "User Intention", "Verdict", "Decision Score", "Confidence",
        "Reality Check", "Main Risk", "Hidden Cost", "Evidence Gap",
        "Red Flag", "Better Move", "Next 24-Hour Action", "Final Truth"
    ]

    target = section_name.lower()
    collected = []
    capture = False

    for raw_line in lines:
        line = clean_voice_text(raw_line)

        if not line:
            continue

        lower = line.lower()

        # Same-line format: Verdict: Avoid
        if lower.startswith(target + ":"):
            value = line.split(":", 1)[1].strip()
            if value:
                collected.append(value)
            capture = True
            continue

        # Header-only format: Verdict
        if lower == target:
            capture = True
            continue

        if capture:
            for section in known_sections:
                section_lower = section.lower()
                if lower.startswith(section_lower + ":") or lower == section_lower:
                    return " ".join(collected).strip()

            collected.append(line)

    return " ".join(collected).strip()


def create_voice_script_from_audit(audit):
    verdict = extract_audit_section(audit, "Verdict") or "Review needed"
    score = extract_audit_section(audit, "Decision Score")
    risk = extract_audit_section(audit, "Main Risk") or extract_audit_section(audit, "Red Flag")
    better = extract_audit_section(audit, "Next 24-Hour Action") or extract_audit_section(audit, "Better Move")
    final_truth = extract_audit_section(audit, "Final Truth")

    script_parts = []

    script_parts.append(f"LifeOS AI verdict: {shorten_voice_part(verdict, 10)}.")

    if score:
        script_parts.append(f"Decision score: {shorten_voice_part(score, 8)}.")

    if risk:
        script_parts.append(f"Main risk: {shorten_voice_part(risk, 28)}.")

    if better:
        script_parts.append(f"Better move: {shorten_voice_part(better, 28)}.")

    if final_truth:
        script_parts.append(f"Final truth: {shorten_voice_part(final_truth, 22)}.")

    script = " ".join(script_parts)
    script = clean_voice_text(script)

    # Strong fallback if section extraction still fails.
    if len(script) < 80:
        plain_lines = []
        for line in audit.splitlines():
            cleaned = clean_voice_text(line)
            if cleaned:
                plain_lines.append(cleaned)

        fallback = " ".join(plain_lines)
        script = "LifeOS AI summary: " + shorten_voice_part(fallback, 85)

    if len(script) > 780:
        script = script[:780].rsplit(" ", 1)[0] + "."

    return script

def telegram_api_multipart(method, fields, file_field, file_path, mime_type="audio/ogg", timeout=90):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")

    boundary = "----LifeOSBoundary" + uuid.uuid4().hex
    url = f"https://api.telegram.org/bot{token}/{method}"

    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    filename = os.path.basename(file_path)
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode())

    with open(file_path, "rb") as f:
        body.extend(f.read())

    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        },
        method="POST"
    )

    return request_with_retry(req, timeout=timeout, retries=3, label="Telegram voice upload")


def send_voice(chat_id, voice_path, caption=None):
    fields = {
        "chat_id": chat_id
    }

    if caption:
        fields["caption"] = caption

    telegram_api_multipart(
        "sendVoice",
        fields,
        "voice",
        voice_path,
        mime_type="audio/ogg",
        timeout=120
    )


def gemini_tts_to_ogg(text_to_speak, audit_id):
    key = os.environ.get("GEMINI_API_KEY")

    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    os.makedirs(VOICE_REPLY_DIR, exist_ok=True)

    safe_id = audit_id.replace("/", "_")
    pcm_path = os.path.join(VOICE_REPLY_DIR, f"{safe_id}.pcm")
    ogg_path = os.path.join(VOICE_REPLY_DIR, f"{safe_id}.ogg")

    # Keep the spoken reply short. Long TTS prompts increase failure risk.
    clean_text = " ".join(text_to_speak.split())
    if len(clean_text) > 550:
        clean_text = clean_text[:550].rsplit(" ", 1)[0] + "."

    speech_prompt = (
        "Speak this as a calm, premium decision advisor. "
        "Use a clear, steady voice. "
        "Do not add extra words. "
        + clean_text
    )

    tts_models = [
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts"
    ]

    last_error = None

    for model_name in tts_models:
        try:
            print(f"Trying TTS model: {model_name}")

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": speech_prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": "Kore"
                            }
                        }
                    }
                }
            }

            data = json.dumps(payload).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": key
                },
                method="POST"
            )

            client = GeminiClient(api_key=key, model=model_name)
            result = client.generate(payload, timeout=60, retries=1, label=f"Gemini voice output {model_name}")

            audio_b64 = None

            try:
                parts = result["candidates"][0]["content"]["parts"]
                for part in parts:
                    inline_data = part.get("inlineData") or part.get("inline_data") or {}
                    if inline_data.get("data"):
                        audio_b64 = inline_data.get("data")
                        break
            except Exception as e:
                last_error = e

            if not audio_b64:
                raise RuntimeError(f"{model_name} did not return audio data.")

            with open(pcm_path, "wb") as f:
                f.write(base64.b64decode(audio_b64))

            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f", "s16le",
                    "-ar", "24000",
                    "-ac", "1",
                    "-i", pcm_path,
                    "-c:a", "libopus",
                    "-b:a", "32k",
                    ogg_path
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )

            print(f"TTS success with model: {model_name}")
            return ogg_path

        except Exception as e:
            last_error = e
            print(f"TTS model failed: {model_name} -> {e}")
            continue

    raise RuntimeError(f"All Gemini TTS fallback models failed. Last error: {last_error}")

def send_audit_voice_summary(chat_id, audit_id, audit):
    try:
        summary = create_voice_script_from_audit(audit)

        if not summary:
            send_message(
                chat_id,
                "Voice summary could not be generated because the audit summary was empty. The written audit is already saved."
            )
            return

        send_message(chat_id, "Voice script to be spoken:\n" + summary)
        send_message(chat_id, "Preparing short voice summary. This may take a moment...")

        voice_path = gemini_tts_to_ogg(summary, audit_id)

        send_voice(chat_id, voice_path)

        send_message(chat_id, f"Voice summary sent.\nAudit ID: {audit_id}")

    except Exception as e:
        print("Voice output error:", str(e))
        send_message(
            chat_id,
            "Voice summary could not be generated right now. The written audit is already saved.\n\nReason:\n" + str(e)
        )


def gemini_audit(user_text, profile):
    key = os.environ.get("GEMINI_API_KEY")

    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    truth_prompt = read_truth_prompt()
    trust_rules = read_trust_rules()
    premium_format = read_premium_format()
    profile_context = profile_context_for_prompt(profile)

    full_prompt = f"""
{truth_prompt}

{trust_rules}

{premium_format}

Premium credibility rules:
- Start with DECISION AUDIT.
- Give a firm verdict.
- Use the saved LifeOS user profile when relevant.
- Do not sound casual.
- Do not overpromise.
- Do not pretend certainty when evidence is weak.
- Keep the advice practical and serious.
- Make the final truth sharp but useful.

{profile_context}

User decision/request to audit:
{user_text}

Return the decision audit now.
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": full_prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.25,
            "topP": 0.8,
            "maxOutputTokens": 1200
        }
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key
        },
        method="POST"
    )

    client = GeminiClient(api_key=key, model=GEMINI_MODEL)
    result = client.generate(payload, timeout=75, retries=4, label="Gemini connection")

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return "GEMINI ERROR: The AI response came back in an unexpected format."


def handle_message(message):
    chat = message.get("chat", {})
    from_user = message.get("from", {})

    chat_id = chat.get("id")
    text = message.get("text", "").strip()

    if not chat_id:
        return

    if message.get("voice") and not text:
        handle_voice_message(message)
        return

    if not text:
        return

    if text == "/start":
        send_message(
            chat_id,
            "Welcome to LifeOS AI.\n\nThis is a personal decision intelligence system.\n\nSend me a decision by text or voice note, and I will audit it before you waste time, money, or momentum.\n\nCommands:\n/test - Check if bot is online\n/help - Show help\n/profile - View saved profile\n/trust - Show LifeOS AI trust rules\n/history - Show recent audits\n/last - Show latest audit\n/showaudit - Retrieve an audit by ID\n/rate - Rate latest audit\n/feedback - Review audit ratings\n/myid - Show your Telegram ID\n/ownerfeedback - Owner-only feedback review"
        )
        return

    if text == "/help":
        send_message(
            chat_id,
            "LifeOS AI commands:\n\n/start - Start the bot\n/help - Show help\n/test - Test if bot is alive\n/profile - View saved LifeOS profile\n/trust - Show trust and safety rules\n/setgoal - Save your main goal\n/setproject - Save your current project\n/setfocus - Save your priority focus\n/setrisk - Save your risk level\n/setmistake - Save your repeated mistake\n/clearmemory - Clear saved profile\n/history - Show your last 5 saved audits\n/last - Show your latest saved audit\n/showaudit - Retrieve a saved audit by ID\n/rate - Rate latest audit\n/feedback - Review audit ratings\n/myid - Show your Telegram ID\n/ownerfeedback - Owner-only feedback review from 1 to 5\n\nExample:\n/setgoal Build LifeOS into a monetized digital product ecosystem\n\nTo audit a decision, send the decision as a text message or Telegram voice note."
        )
        return

    if text == "/test":
        send_message(chat_id, "LifeOS AI is online. Engine ready. Profile memory, trust rules, and premium audit history are active.")
        return

    if text == "/trust":
        send_message(
            chat_id,
            "LIFEOS AI TRUST RULES\n\n"
            "LifeOS AI provides decision intelligence, not professional legal, financial, medical, or emergency advice.\n\n"
            "It audits decisions using honesty, risk awareness, evidence limits, practical next steps, and personal context.\n\n"
            "It must not flatter blindly, pretend certainty, encourage reckless action, or store private secrets."
        )
        return

    if text == "/history":
        records = load_recent_audits(chat_id, limit=5)
        send_message(chat_id, format_history(records))
        return

    if text == "/last":
        records = load_recent_audits(chat_id, limit=1)

        if not records:
            send_message(chat_id, "No saved audit found yet.")
            return

        record = records[0]
        send_message(
            chat_id,
            f"LATEST LIFEOS AI AUDIT\n\nAudit ID: {record.get('audit_id')}\nTime: {record.get('timestamp_utc')}\nDecision: {record.get('user_text')}\n\nUse /history to see more."
        )
        return

    if text == "/myid":
        send_message(
            chat_id,
            f"Your Telegram ID: {from_user.get('id')}\nChat ID: {chat_id}"
        )
        return

    if text == "/ownerfeedback":
        if not is_admin_user(chat_id, from_user):
            send_message(chat_id, "Owner-only command. Access denied.")
            return

        records = load_all_feedback(limit=20)
        send_message(chat_id, format_owner_feedback(records))
        return

    if text == "/feedback":
        records = load_recent_feedback(chat_id, limit=10)
        send_message(chat_id, format_feedback(records))
        return

    if text.startswith("/rate"):
        value = command_value(text, "/rate")

        if not value:
            send_message(chat_id, "Use it like this:\n/rate 5\n\nOptional:\n/rate 4 Useful, but too long")
            return

        parts = value.split(" ", 1)
        rating_text = parts[0].strip()
        note = parts[1].strip() if len(parts) > 1 else ""

        if rating_text not in ["1", "2", "3", "4", "5"]:
            send_message(chat_id, "Rating must be a number from 1 to 5.\n\nUse it like this:\n/rate 5")
            return

        latest = load_recent_audits(chat_id, limit=1)

        if not latest:
            send_message(chat_id, "No saved audit found to rate yet.")
            return

        latest_audit = latest[0]

        feedback_record = {
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "chat_id": chat_id,
            "user_id": from_user.get("id"),
            "username": from_user.get("username"),
            "audit_id": latest_audit.get("audit_id"),
            "rating": int(rating_text),
            "note": note
        }

        save_feedback(feedback_record)

        send_message(
            chat_id,
            f"Audit feedback saved.\n\nAudit ID: {latest_audit.get('audit_id')}\nRating: {rating_text}/5"
        )
        return

    if text.startswith("/showaudit"):
        audit_id = command_value(text, "/showaudit")

        if not audit_id:
            send_message(chat_id, "Use it like this:\n/showaudit LOS-20260519-234500-A1B2C3")
            return

        record = find_audit_by_id(chat_id, audit_id)

        if not record:
            send_message(chat_id, "No saved audit found with that Audit ID.")
            return

        send_message(chat_id, format_saved_audit(record))
        return

    if text == "/profile":
        profile = get_profile(chat_id)
        send_message(chat_id, format_profile(profile))
        return

    if text.startswith("/setgoal"):
        value = command_value(text, "/setgoal")
        if not value:
            send_message(chat_id, "Use it like this:\n/setgoal Build LifeOS into a monetized digital product ecosystem")
            return
        update_profile(chat_id, "main_goal", value)
        send_message(chat_id, "Main goal saved.")
        return

    if text.startswith("/setproject"):
        value = command_value(text, "/setproject")
        if not value:
            send_message(chat_id, "Use it like this:\n/setproject LifeOS AI decision intelligence bot")
            return
        update_profile(chat_id, "current_project", value)
        send_message(chat_id, "Current project saved.")
        return

    if text.startswith("/setfocus"):
        value = command_value(text, "/setfocus")
        if not value:
            send_message(chat_id, "Use it like this:\n/setfocus Build the MVP and test real users")
            return
        update_profile(chat_id, "priority_focus", value)
        send_message(chat_id, "Priority focus saved.")
        return

    if text.startswith("/setrisk"):
        value = command_value(text, "/setrisk")
        if not value:
            send_message(chat_id, "Use it like this:\n/setrisk Medium")
            return
        update_profile(chat_id, "risk_level", value)
        send_message(chat_id, "Risk level saved.")
        return

    if text.startswith("/setmistake"):
        value = command_value(text, "/setmistake")
        if not value:
            send_message(chat_id, "Use it like this:\n/setmistake Starting too many projects before finishing the core build")
            return
        update_profile(chat_id, "repeated_mistake", value)
        send_message(chat_id, "Repeated mistake saved.")
        return

    if text == "/clearmemory":
        clear_profile(chat_id)
        send_message(chat_id, "LifeOS AI profile memory cleared.")
        return

    audit_id = create_audit_id()
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    profile = get_profile(chat_id)

    send_message(chat_id, f"Auditing your decision now...\nAudit ID: {audit_id}")

    try:
        audit = gemini_audit(text, profile)

        premium_response = f"Audit ID: {audit_id}\nTimestamp: {timestamp_utc}\n\n{audit}"

        record = {
            "audit_id": audit_id,
            "timestamp_utc": timestamp_utc,
            "chat_id": chat_id,
            "user_id": from_user.get("id"),
            "username": from_user.get("username"),
            "first_name": from_user.get("first_name"),
            "user_text": text,
            "profile_snapshot": profile,
            "audit": audit
        }

        save_audit(record)
        send_message(chat_id, premium_response)
        send_message(chat_id, "Generating voice summary...")
        send_audit_voice_summary(chat_id, audit_id, audit)

    except Exception as e:
        send_message(
            chat_id,
            "LifeOS AI hit a connection or AI error after retrying.\n\nThe bot is still running.\n\nError:\n" + str(e)
        )


def main():
    load_env_file(ENV_FILE)

    print("Starting LifeOS AI Telegram bot...")
    print("Loading secure keys...")

    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY missing.")
        return

    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("ERROR: TELEGRAM_BOT_TOKEN missing.")
        return

    print("Keys loaded.")
    print("Retry protection: ON")
    print("Premium audit history: ON")
    print("Profile memory: ON")
    print("Bot is polling Telegram.")
    print("Press CTRL + C to stop.")

    offset = None

    while True:
        try:
            payload = {
                "timeout": 30
            }

            if offset is not None:
                payload["offset"] = offset

            result = telegram_api("getUpdates", payload=payload, timeout=45)

            if result.get("ok"):
                updates = result.get("result", [])

                for update in updates:
                    offset = update["update_id"] + 1

                    if "message" in update:
                        handle_message(update["message"])

            time.sleep(1)

        except KeyboardInterrupt:
            print("\nLifeOS AI stopped by user.")
            break

        except Exception as e:
            print("Runtime error:", str(e))
            print("Bot is still alive. Retrying in 5 seconds...")
            time.sleep(5)


if __name__ == "__main__":
    main()
