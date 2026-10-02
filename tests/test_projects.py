import json
import unittest
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from digest.projects import fetch_projects, trending_repositories

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
REPO = {"full_name": "owner/agent-skills", "html_url": "https://github.com/owner/agent-skills", "description": "Reusable AI skills", "stargazers_count": 1200, "pushed_at": "2026-09-30T00:00:00Z", "license": {"spdx_id": "MIT"}, "language": "Python"}


class ProjectTests(unittest.TestCase):
    def test_theme_rotation_and_new_project_window_are_sent_to_real_search(self):
        source = {"name": "GitHub", "kind": "github_search", "url": "https://api.github.com/search/repositories",
                  "queries": ["agent stars:>=300", "mcp stars:>=300", "automation stars:>=300"], "created_days": 90, "scan_limit": 20}
        calls = []
        def fetch(url):
            calls.append(url)
            return json.dumps({"items": [REPO]}).encode()
        records = fetch_projects(source, NOW, fetch)
        self.assertEqual(len(calls), 2)
        queries = [parse_qs(urlsplit(url).query)["q"][0] for url in calls]
        self.assertNotEqual(queries[0], queries[1])
        self.assertTrue(all('created:>=2026-07-04' in q and 'pushed:>=2026-04-05' in q for q in queries))
        self.assertEqual(records[0]["discovery"], "topic_search")
        self.assertIsNone(records[0]["stars_today"])

    def test_one_failed_search_preserves_other_search_results(self):
        source = {"name": "GitHub", "kind": "github_search", "url": "https://api.github.com/search/repositories", "queries": ["agent", "skill"]}
        calls, failures = [], []
        def fetch(url):
            calls.append(url)
            if len(calls) == 1:
                raise TimeoutError()
            return json.dumps({"items": [REPO]}).encode()
        self.assertEqual(len(fetch_projects(source, NOW, fetch, failures)), 1)
        self.assertEqual(failures, ["TimeoutError"])

    def test_trending_growth_comes_from_same_repository_card(self):
        body = b'<article><h2><a href="/owner/agent-skills">agent-skills</a></h2><p>Reusable AI agent skills and automation workflows for everyday work.</p><span>1,234 stars today</span></article><article><a href="/other/skills">skills</a><span>12 stars today</span></article>'
        self.assertEqual(trending_repositories(body), [("owner/agent-skills", 1234), ("other/skills", 12)])

    def test_search_does_not_invent_growth_or_release_date(self):
        source = {"name": "GitHub", "kind": "github_search", "category": "github", "url": "https://api.github.com/search/repositories"}
        records = fetch_projects(source, NOW, lambda u: json.dumps({"items": [REPO, dict(REPO, archived=True)]}).encode())
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["stars_today"])
        self.assertEqual(records[0]["date_precision"], "observed")
        self.assertEqual(records[0]["pushed_at"], REPO["pushed_at"])
        self.assertEqual(records[0]["stars"], 1200)

    def test_low_star_search_repository_not_selected(self):
        source = {"name": "GitHub", "kind": "github_search", "url": "https://api.github.com/search/repositories"}
        self.assertEqual(fetch_projects(source, NOW, lambda u: json.dumps({"items": [dict(REPO, stargazers_count=20)]}).encode()), [])
