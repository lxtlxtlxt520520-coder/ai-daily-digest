import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from digest.run import StopRun, build_messages, chunks, execute, load_seen, validate_result

NOW = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
CONFIG = {"model": "deepseek-flash", "max_input_bytes": 12000, "max_output_tokens": 3200}
CANDIDATES = [{"id": "C001", "title": "An AI model release", "summary": "A model is released.", "source": "Official", "kind": "rss", "published": "2026-10-01T12:00:00+00:00", "url": "https://example.com/release", "keys": ["url:a", "title:a"]}]
RESULT = {"items": [{"title": "模型发布", "summary": "官方公布新模型，具体能力可查看原文。", "source_ids": ["C001"]}]}


def response(result=RESULT, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": json.dumps(result)}}]}


class RunTests(unittest.TestCase):
    def test_success_preserves_source_and_caches_news_not_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seen.json"
            sent, calls = [], []
            def model(payload):
                calls.append(payload)
                return response()
            text, stats = execute(CONFIG, CANDIDATES, [], path, model, sent.append, NOW)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["thinking"], {"type": "disabled"})
            self.assertEqual(calls[0]["max_tokens"], 3200)
            self.assertEqual(stats["items"], 1)
            self.assertIn("https://example.com/release", text)
            self.assertEqual(set(load_seen(path)), {"url:a", "title:a"})
            self.assertEqual(sent, [text])
            self.assertNotIn("费用", text)

    def test_timeout_is_not_retried(self):
        calls = []
        def model(payload):
            calls.append(payload)
            raise TimeoutError()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):
                execute(CONFIG, CANDIDATES, [], Path(directory) / "seen.json", model, lambda text: self.fail("must not send"), NOW)
        self.assertEqual(len(calls), 1)

    def test_hallucinated_or_reused_source_rejected(self):
        unknown = copy.deepcopy(RESULT)
        unknown["items"][0]["source_ids"] = ["C999"]
        duplicate = {"items": RESULT["items"] * 2}
        for raw in [unknown, duplicate]:
            with self.assertRaises(StopRun):
                validate_result(raw, {"C001"})

    def test_truncated_output_never_sent(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(StopRun):
                execute(CONFIG, CANDIDATES, [], Path(directory) / "seen.json", lambda payload: response(finish="length"), lambda text: self.fail("must not send"), NOW)

    def test_prompt_cap_handles_multibyte_text(self):
        candidates = [dict(CANDIDATES[0], id="C" + str(i), summary="新模型" * 150) for i in range(40)]
        messages, selected = build_messages(candidates, CONFIG)
        self.assertLessEqual(sum(len(m["content"].encode()) for m in messages), 12000)
        self.assertGreater(len(selected), 1)
        self.assertLess(len(selected), 40)

    def test_telegram_utf16_limits(self):
        text = "\n".join(["😀" * 800] * 6)
        parts = chunks(text)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p.encode("utf-16-le")) // 2 <= 3500 for p in parts))
        with self.assertRaises(StopRun):
            chunks("a" * 3501)

    def test_send_timeout_keeps_attempted_news_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seen.json"
            def send(text):
                raise TimeoutError()
            with self.assertRaises(TimeoutError):
                execute(CONFIG, CANDIDATES, [], path, lambda payload: response(), send, NOW)
            self.assertIn("url:a", load_seen(path))

    def test_no_candidates_never_calls_model(self):
        with self.assertRaises(StopRun):
            execute(CONFIG, [], [], Path("unused.json"), lambda payload: self.fail("must not call"), lambda text: self.fail("must not send"), NOW)
