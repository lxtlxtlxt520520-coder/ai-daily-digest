import unittest
from datetime import datetime, timezone
from digest.collect import canonical_url, collect, parse_feed

NOW = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
SOURCE = {"name": "test", "kind": "rss", "url": "https://example.com/rss"}
RSS = b'''<rss><channel><item><title>New AI model</title><link>https://example.com/new?utm_source=test</link><pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate><description>Announcement</description></item><item><title>Old news</title><link>https://example.com/old</link><pubDate>Wed, 01 Oct 2025 12:00:00 GMT</pubDate></item><item><title>Undated</title><link>https://example.com/no-date</link></item></channel></rss>'''


class CollectionTests(unittest.TestCase):
    def test_source_window_and_rdf_date_do_not_fake_freshness(self):
        rdf = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/"><item><title>Health research</title><link>https://example.com/health</link><dc:date>2026-09-20</dc:date><content:encoded>Human study</content:encoded></item></rdf:RDF>'''
        source = dict(SOURCE, category="health", window_hours=720)
        config = {"sources": [source], "window_hours": 24, "max_candidates": 40}
        candidates, _ = collect(config, NOW, fetch=lambda url: rdf)
        self.assertEqual(candidates[0]["category"], "health")
        self.assertEqual(candidates[0]["published"], "2026-09-20T00:00:00+00:00")
        self.assertEqual(candidates[0]["summary"], "Human study")
        config["sources"][0] = SOURCE
        self.assertEqual(collect(config, NOW, fetch=lambda url: rdf)[0], [])

    def test_dates_and_tracking_links(self):
        records = parse_feed(RSS, SOURCE)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["url"], "https://example.com/new")

    def test_old_duplicate_and_previously_sent_filtered(self):
        config = {"sources": [SOURCE, dict(SOURCE, name="duplicate")], "window_hours": 24, "max_candidates": 40}
        candidates, reports = collect(config, NOW, fetch=lambda url: RSS)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(reports), 2)
        again, _ = collect(config, NOW, candidates[0]["keys"], fetch=lambda url: RSS)
        self.assertEqual(again, [])

    def test_atom_prefers_publish_date_to_updated(self):
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Video</title><published>2025-01-01T00:00:00Z</published><updated>2026-10-01T00:00:00Z</updated><link rel="self" href="https://example.com/xml"/><link rel="alternate" href="https://example.com/video"/></entry></feed>'''
        record = parse_feed(atom, SOURCE)[0]
        self.assertTrue(record["published"].startswith("2025"))
        self.assertEqual(record["url"], "https://example.com/video")

    def test_dangerous_xml_and_urls_rejected(self):
        with self.assertRaises(ValueError):
            parse_feed(b'<!DOCTYPE rss><rss/>', SOURCE)
        for url in ["javascript:alert(1)", "https://user:secret@example.com", "file:///etc/passwd"]:
            with self.assertRaises(ValueError):
                canonical_url(url)

    def test_failed_feed_does_not_silently_look_successful(self):
        _, reports = collect({"sources": [SOURCE], "window_hours": 24, "max_candidates": 40}, NOW, fetch=lambda url: b'bad')
        self.assertEqual(reports[0]["status"], "failed")
