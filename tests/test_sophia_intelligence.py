"""Regression contracts for Sophia language intelligence and the app shell."""

import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from app.gemini_client import GeminiClient
from app.lifeos_public_tts import build_voice_prompt, spoken_language
from app.sophia_intelligence import (
    CHAT_ASSISTANT_CHARACTER_LIMIT,
    CHAT_CONTEXT_MESSAGES,
    CHAT_USER_CHARACTER_LIMIT,
    SOPHIA_CHAT_SYSTEM_INSTRUCTION,
    compact_chat_messages,
    gemini_chat_contents,
)


ROOT = Path(__file__).resolve().parents[1]


class SophiaLanguagePolicyTests(unittest.TestCase):
    def test_identity_language_and_igbo_policy_are_explicit(self):
        policy = SOPHIA_CHAT_SYSTEM_INSTRUCTION
        self.assertIn(
            "Sophia, the LifeOSAI Synthetic Artificial Intelligence assistant",
            policy,
        )
        self.assertIn("Infer meaning from the whole utterance", policy)
        self.assertIn("Never silently change a person's name", policy)
        self.assertIn("Treat Igbo as a first-class conversation language", policy)
        self.assertIn("omitted tone marks", policy)
        self.assertIn("natural code-switching", policy)
        self.assertIn("ask one precise clarification in Igbo", policy)

    def test_chat_context_is_bounded_without_flattening_roles(self):
        supplied = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"turn {index}"}
            for index in range(18)
        ]
        supplied[-2]["content"] = "u" * (CHAT_USER_CHARACTER_LIMIT + 100)
        supplied[-1]["content"] = "a" * (CHAT_ASSISTANT_CHARACTER_LIMIT + 100)

        compacted = compact_chat_messages(supplied)

        self.assertEqual(len(compacted), CHAT_CONTEXT_MESSAGES)
        self.assertEqual(len(compacted[-2]["content"]), CHAT_USER_CHARACTER_LIMIT)
        self.assertEqual(
            len(compacted[-1]["content"]),
            CHAT_ASSISTANT_CHARACTER_LIMIT,
        )
        self.assertEqual(
            [item["role"] for item in gemini_chat_contents(compacted)[-2:]],
            ["user", "model"],
        )

    def test_transient_assistant_failures_are_not_reintroduced(self):
        compacted = compact_chat_messages(
            [
                {"role": "user", "content": "Gịnị ka nke a pụtara?"},
                {
                    "role": "assistant",
                    "content": "Sophia is reviewing the decision thread.",
                },
                {"role": "user", "content": "Kọwaa ya nke ọma."},
            ]
        )
        self.assertEqual(len(compacted), 2)
        self.assertTrue(all(item["role"] == "user" for item in compacted))

    def test_chat_requires_real_user_content(self):
        with self.assertRaisesRegex(ValueError, "user message"):
            compact_chat_messages([{"role": "assistant", "content": "Hello"}])

    def test_igbo_tts_hint_preserves_igbo_delivery(self):
        text = "Biko, kọwaa ihe a nke ọma."
        prompt = build_voice_prompt(text, "ig-NG")
        self.assertEqual(spoken_language(text, "ig-NG"), "ig-NG")
        self.assertIn("natural Igbo pronunciation", prompt)
        self.assertIn("Do not apply a London-English accent", prompt)
        self.assertIn("Text to read: " + text, prompt)
        self.assertNotIn("London English female", prompt)


class GeminiNativeConversationTests(unittest.TestCase):
    def test_grounded_request_keeps_native_turns_and_system_instruction(self):
        client = GeminiClient(api_key="test-key")
        contents = [
            {"role": "user", "parts": [{"text": "Kedu?"}]},
            {"role": "model", "parts": [{"text": "Ọ dị mma."}]},
            {"role": "user", "parts": [{"text": "Gịnị mere?"}]},
        ]
        captured = {}

        def fake_request(body, timeout, retries, **kwargs):
            captured["body"] = body
            return (
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "Nke a bụ azịza."}]}}
                    ]
                },
                "gemini-test",
            )

        with mock.patch.object(client, "_request", side_effect=fake_request):
            result = client.generate_grounded_text(
                contents=contents,
                system_instruction="Remain Sophia and answer in Igbo.",
            )

        self.assertEqual(result["text"], "Nke a bụ azịza.")
        self.assertEqual(captured["body"]["contents"], contents)
        self.assertEqual(
            captured["body"]["systemInstruction"],
            {"parts": [{"text": "Remain Sophia and answer in Igbo."}]},
        )
        self.assertEqual(captured["body"]["tools"], [{"google_search": {}}])


class SophiaAppShellTests(unittest.TestCase):
    def test_app_shell_runtime_keeps_public_and_installed_navigation_separate(self):
        result = subprocess.run(
            ["node", str(ROOT / "tests/test_sophia_app_shell.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_manifest_launches_installed_app_in_sophia_chat(self):
        manifest = json.loads(
            (ROOT / "web/lifeos_voice/manifest.webmanifest").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["id"], "/")
        self.assertEqual(manifest["start_url"], "/chat?source=pwa")
        self.assertEqual(
            manifest["name"],
            "LifeOSAI — Sophia Synthetic Artificial Intelligence",
        )

    def test_app_mode_redirect_and_logo_navigation_are_scoped(self):
        shell = (
            ROOT / "web/lifeos_voice/assets/lifeos_pwa_v1.js"
        ).read_text(encoding="utf-8")
        chat = (ROOT / "web/lifeos_voice/chat.html").read_text(encoding="utf-8")

        self.assertIn("android-app:\\/\\/losia", shell)
        self.assertIn('const appHomeUrl = isAppMode ? "/chat?source=app" : "/"', shell)
        self.assertIn('location.replace(appHomeUrl)', shell)
        self.assertIn("window.LifeOSAppShell", shell)
        self.assertIn("window.LifeOSAppShell?.homeUrl", chat)

    def test_chat_exposes_igbo_recognition_without_output_voice_override(self):
        chat = (ROOT / "web/lifeos_voice/chat.html").read_text(encoding="utf-8")
        self.assertIn('<option value="ig-NG">Igbo (Nigeria)</option>', chat)
        self.assertIn("lifeosRecognition.lang = currentSpeechLanguage()", chat)
        self.assertIn("applySpeechRecognitionLanguage(input.value)", chat)
        self.assertIn(".slice(-12)", chat)
        self.assertNotIn('lifeosRecognition.lang = "en-NG"', chat)
        self.assertNotIn("lifeosRecognition.lang = selectedVoice.lang", chat)


if __name__ == "__main__":
    unittest.main()
