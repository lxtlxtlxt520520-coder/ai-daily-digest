import json
import ipaddress
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from digest.collect import PublicRedirect, collect, public_url
from digest.discovery import daily_queries, fetch_discussions

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
SOURCE = {"name": "Topic search", "kind": "hn_search", "category": "ai_tips", "url": "https://hn.algolia.com/api/v1/search",
          "queries": ["workflow", "prompt", "Codex"], "window_hours": 720, "scan_limit": 3, "limit": 3}


class DiscoveryTests(unittest.TestCase):
    def test_queries_rotate_by_beijing_day_not_execution_timezone(self):
        before = datetime(2026, 10, 1, 15, 59, tzinfo=timezone.utc)
        after = datetime(2026, 10, 1, 16, tzinfo=timezone.utc)
        self.assertNotEqual(daily_queries(SOURCE, before), daily_queries(SOURCE, after))
        self.assertEqual(daily_queries(SOURCE, after), daily_queries(SOURCE, NOW))

    def test_search_reads_different_publishers_and_does_not_use_submission_date(self):
        calls, failures = [], []
        def fetch(url):
            calls.append(url)
            if url.startswith(SOURCE["url"]):
                query = parse_qs(urlsplit(url).query)["query"][0]
                return json.dumps({"hits": [{"url": "https://" + query + ".example/article", "title": "Practical workflow",
                                              "objectID": "123", "points": 50, "created_at": "2026-10-01T12:00:00Z"}]}).encode()
            return b'<h1>Original workflow</h1><meta property="article:published_time" content="2026-09-24T00:00:00Z"><p>Use this concrete example to build an effective workflow. It explains specific steps and discusses its limitations.</p>'
        records = fetch_discussions(SOURCE, NOW, fetch, failures)
        self.assertEqual(len(records), 2)
        self.assertEqual(len({r["publisher"] for r in records}), 2)
        self.assertEqual(records[0]["published"][:10], "2026-09-24")
        self.assertEqual(records[0]["discussion_points"], 50)
        self.assertEqual(failures, [])
        self.assertIn("numericFilters=", calls[0])

    def test_undated_original_is_not_treated_as_new(self):
        def fetch(url):
            if url.startswith(SOURCE["url"]):
                return json.dumps({"hits": [{"url": "https://example.com/article", "title": "Workflow", "objectID": "1", "created_at": NOW.isoformat()}]}).encode()
            return b'<h1>Undated workflow</h1><p>Useful information without publication metadata must not inherit a current search date.</p>'
        self.assertEqual(fetch_discussions(SOURCE, NOW, fetch, []), [])

    def test_sent_candidates_do_not_use_up_source_quota(self):
        feed = '<rss><channel>' + ''.join('<item><title>Article ' + str(i) + '</title><link>https://example.com/' + str(i) + '</link><pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate></item>' for i in range(3)) + '</channel></rss>'
        config = {"sources": [{"name": "Feed", "kind": "rss", "url": "https://example.com/rss", "limit": 1}], "window_hours": 48, "max_candidates": 5}
        first, _ = collect(config, NOW, fetch=lambda u: feed.encode())
        second, _ = collect(config, NOW, first[0]["keys"], fetch=lambda u: feed.encode())
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["url"], second[0]["url"])

    def test_private_networks_and_unsafe_redirects_are_blocked(self):
        with patch("digest.collect.socket.getaddrinfo", return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(ValueError):
                public_url("https://local.example/article")
            with self.assertRaises(ValueError):
                PublicRedirect().redirect_request(None, None, 302, "", {}, "https://local.example/article")
        for url in ["http://example.com/article", "https://key@example.com/article", "https://example.com:8443/article"]:
            with self.assertRaises(ValueError):
                public_url(url)
        with patch("digest.collect.socket.getaddrinfo", return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]):
            public_url("https://example.com/article")

    def test_synthetic_proxy_dns_still_requires_verified_public_destination(self):
        with patch("digest.collect.socket.getaddrinfo", return_value=[(2, 1, 6, '', ('198.18.0.28', 443))]):
            with patch("digest.collect.proxy_addresses", return_value=[ipaddress.ip_address('8.8.8.8')]):
                public_url("https://example.com/article")
            with patch("digest.collect.proxy_addresses", return_value=[ipaddress.ip_address('10.0.0.1')]):
                with self.assertRaises(ValueError):
                    public_url("https://example.com/article")
            with self.assertRaises(ValueError):
                public_url("https://198.18.0.28/article")
