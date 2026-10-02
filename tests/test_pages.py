import unittest
from digest.pages import Page, article_metadata, dated, fetch_articles, fetch_x_excerpts


class PageTests(unittest.TestCase):
    def test_one_failed_article_preserves_other_article_and_reports_failure(self):
        failures = []
        def fetch(url):
            if url.endswith("/news"):
                return b'<a href="/news/blocked">Blocked</a><a href="/news/good">Good</a>'
            if url.endswith("blocked"):
                raise TimeoutError()
            return b'<h1>Good</h1><meta property="article:published_time" content="2026-10-01T00:00:00Z">'
        records = fetch_articles({"url": "https://example.com/news", "article_pattern": r"/news/[a-z-]+", "name": "test", "kind": "articles"}, fetch, failures)
        self.assertEqual(len(records), 1)
        self.assertEqual(failures, ["TimeoutError"])

    def test_x_excerpt_only_uses_allowed_authors_and_labels_unverified_heat(self):
        body = b'''<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><link>https://news.smol.ai/issues/report</link><pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate><content:encoded><![CDATA[<li>Practical example <a href="https://twitter.com/simonw/status/123">@simonw</a></li><li>Other <a href="https://x.com/advertiser/status/456">Ad</a></li>]]></content:encoded></item></channel></rss>'''
        source = {"name": "Community", "kind": "x_excerpts", "category": "ai_tips", "url": "https://news.smol.ai/rss.xml", "authors": ["simonw"]}
        records = fetch_x_excerpts(source, lambda u: body)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["url"], "https://x.com/simonw/status/123")
        self.assertFalse(records[0]["heat_verified"])
        self.assertEqual(records[0]["evidence_type"], "community_excerpt")

    def test_metadata_prefers_publication_over_modification_and_keeps_excerpt(self):
        page = Page(b'''<h1>Research title</h1><script type="application/ld+json">{"@graph":[{"@type":"Article","datePublished":"2026-09-20","dateModified":"2026-10-02","description":"Human participants"}]}</script><p>A study with human participants describes an association and its limitations.</p>''')
        title, date, excerpt = article_metadata(page)
        self.assertEqual(title, "Research title")
        self.assertEqual(date.isoformat(), "2026-09-20T00:00:00+00:00")
        self.assertIn("limitations", excerpt)

    def test_listing_cannot_fetch_external_links_or_invent_dates(self):
        requests = []
        def fetch(url):
            requests.append(url)
            if url.endswith("/news"):
                return b'<a href="https://other.example/news/steal">External</a><a href="/news/article">Undated article</a>'
            return b'<h1>Undated article</h1><p>This has useful content, but no identifiable publication date.</p>'
        self.assertEqual(fetch_articles({"url": "https://example.com/news", "article_pattern": r"/news/[a-z-]+", "name": "test", "kind": "articles"}, fetch), [])
        self.assertEqual(requests, ["https://example.com/news", "https://example.com/news/article"])

    def test_newsletter_date_from_publisher_url(self):
        source = {"url": "https://example.com/3-2-1", "article_pattern": r"/3-2-1/[a-z]+-\d+-\d{4}", "name": "growth", "kind": "articles", "category": "growth"}
        pages = {source["url"]: b'<a href="/3-2-1/september-24-2026">Ideas</a>', "https://example.com/3-2-1/september-24-2026": b'<h1>Ideas</h1><p>A clear explanation of a practical habit and a step that someone can try.</p>'}
        record = fetch_articles(source, pages.__getitem__)[0]
        self.assertEqual(record["published"][:10], "2026-09-24")
        self.assertEqual(record["category"], "growth")

    def test_bad_calendar_date_rejected(self):
        self.assertIsNone(dated("September 99, 2026"))
