import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from digest.run import StopRun, build_messages, chunks, execute, load_seen, model_url, validate_result

NOW = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
CONFIG = {"model": "gpt-6.1-sol", "reasoning_effort": "medium", "max_input_bytes": 12000, "max_completion_tokens": 8192}
CANDIDATES = [{"id": "C001", "title": "An AI model release", "summary": "A model is released.", "source": "Official", "kind": "rss", "published": "2026-10-01T12:00:00+00:00", "url": "https://example.com/release", "keys": ["url:a", "title:a"]}]
RESULT = {"items": [{"title": "模型发布", "summary": "官方公布新模型，具体能力可查看原文。", "source_ids": ["C001"]}]}


def response(result=RESULT, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": json.dumps(result)}}]}


class RunTests(unittest.TestCase):
    def test_different_publishers_get_prompt_space_before_one_authors_later_posts(self):
        candidates = [dict(CANDIDATES[0], id="A" + str(i), category="ai_tips", publisher="author-a", summary="practical workflow " * 40) for i in range(30)]
        candidates += [dict(CANDIDATES[0], id="B", category="ai_tips", publisher="new-author", discovery="topic_search", evidence_type="original_excerpt", discussion_points=80)]
        messages, ids = build_messages(candidates, CONFIG)
        self.assertIn("B", ids)
        evidence = next(c for c in json.loads(messages[1]["content"])["candidates"] if c["id"] == "B")
        self.assertEqual(evidence["discovery"], "topic_search")
        self.assertEqual(evidence["discussion_points"], 80)
        self.assertLessEqual(sum(len(m["content"].encode()) for m in messages), CONFIG["max_input_bytes"])

    def test_search_results_keep_original_excerpt_and_community_heat_distinct(self):
        from digest.run import render
        candidates = [dict(CANDIDATES[0], category="research", publisher="Journal", evidence_type="research_abstract", discussion_points=50)]
        items = [dict(RESULT["items"][0], category="research", evidence_note="原论文摘要，不能推断因果。")]
        text = render(items, candidates, [], NOW, {"research": 1})
        self.assertIn("原论文摘要，未阅读全文", text)
        self.assertIn("HN社区分数 50", text)

    def test_curated_quotas_and_source_category_are_enforced(self):
        candidates = [dict(CANDIDATES[0], category="github"), dict(CANDIDATES[0], id="C002", category="health")]
        selected = dict(RESULT["items"][0], category="github", action="查看原仓库的上手说明。", evidence_note="项目描述与GitHub星数。")
        limits = {"github": 1, "health": 1}
        result = validate_result({"items": [selected]}, {"C001", "C002"}, candidates, limits)
        self.assertEqual(result[0]["category"], "github")
        wrong = dict(selected, category="health")
        extra = dict(selected, source_ids=["C002"])
        for items in ([wrong], [selected, extra]):
            with self.assertRaises(StopRun):
                validate_result({"items": items}, {"C001", "C002"}, candidates, limits)
        candidates[1]["category"] = "github"
        with self.assertRaisesRegex(StopRun, "quota"):
            validate_result({"items": [selected, extra]}, {"C001", "C002"}, candidates, limits)

    def test_minor_ai_and_research_without_evidence_are_not_sent(self):
        for category in ("major_ai", "health", "research", "psychology"):
            candidates = [dict(CANDIDATES[0], category=category)]
            item = dict(RESULT["items"][0], category=category)
            with self.assertRaises(StopRun):
                validate_result({"items": [item]}, {"C001"}, candidates, {category: 1})
            item.update(major=True, evidence_note="摘录未提供研究对象和方法，不能推断因果。")
            self.assertEqual(len(validate_result({"items": [item]}, {"C001"}, candidates, {category: 1})), 1)

    def test_prompt_gives_all_sections_a_chance_under_size_limit(self):
        candidates = [dict(CANDIDATES[0], id="G" + str(i), category="github", summary="工具" * 200) for i in range(30)]
        candidates += [dict(CANDIDATES[0], id="H", category="health")]
        messages, ids = build_messages(candidates, CONFIG)
        self.assertIn("H", ids)
        self.assertLessEqual(sum(len(m["content"].encode()) for m in messages), CONFIG["max_input_bytes"])

    def test_curated_render_labels_observed_stars_and_missing_slots(self):
        from digest.run import render
        candidates = [dict(CANDIDATES[0], category="github", date_precision="observed", stars=1200, stars_today=None)]
        items = [dict(RESULT["items"][0], category="github", action="阅读上手说明。", evidence_note="项目资料。")]
        text = render(items, candidates, [], NOW, {"github": 3, "ai_tips": 2})
        self.assertIn("热度采样", text)
        self.assertIn("⭐ 1200", text)
        self.assertNotIn("今日新增", text)
        self.assertIn("GitHub 项目 1/3", text)
        self.assertIn("不代表高赞排名", text)

    def test_model_endpoint_uses_configured_provider_path(self):
        self.assertEqual(model_url({"api_base": "https://api.790053500.com/v1/"}), "https://api.790053500.com/v1/chat/completions")
        for base in ["http://example.com/v1", "https://key@example.com/v1", "https://example.com/v1?key=private", "https://example.com/v1#fragment"]:
            with self.assertRaises(StopRun):
                model_url({"api_base": base})

    def test_success_preserves_source_and_caches_news_not_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seen.json"
            sent, calls = [], []
            def model(payload):
                calls.append(payload)
                return response()
            text, stats = execute(CONFIG, CANDIDATES, [], path, model, sent.append, NOW)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["model"], "gpt-6.1-sol")
            self.assertEqual(calls[0]["reasoning_effort"], "medium")
            self.assertEqual(calls[0]["max_completion_tokens"], 8192)
            for unsupported in ["thinking", "temperature", "max_tokens"]:
                self.assertNotIn(unsupported, calls[0])
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
