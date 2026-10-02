import json
import unittest
from datetime import datetime, timezone
from digest.projects import fetch_projects, trending_repositories

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
REPO = {"full_name": "owner/agent-skills", "html_url": "https://github.com/owner/agent-skills", "description": "Reusable AI skills", "stargazers_count": 1200, "pushed_at": "2026-09-30T00:00:00Z", "license": {"spdx_id": "MIT"}, "language": "Python"}


class ProjectTests(unittest.TestCase):
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
