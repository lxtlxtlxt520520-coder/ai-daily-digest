"""Read bounded public article lists and metadata without executing page scripts."""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .collect import canonical_url, clean, item, parse_date


class Page(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.links, self.paragraphs, self.meta, self.dates, self.structured = [], [], {}, [], []
        self.active = {}
        self.feed(body.decode("utf-8", errors="replace"))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta[attrs.get("property", attrs.get("name", ""))] = attrs.get("content", "")
        if tag == "time" and attrs.get("datetime"):
            self.dates.append(attrs["datetime"])
        if tag in {"a", "p", "h1"} or (tag == "script" and attrs.get("type") == "application/ld+json"):
            self.active[tag] = [attrs, ""]

    def handle_data(self, text):
        for value in self.active.values():
            value[1] += text

    def handle_endtag(self, tag):
        value = self.active.pop(tag, None)
        if value is None:
            return
        attrs, text = value
        if tag == "a":
            self.links.append((attrs.get("href", ""), clean(text, 400)))
        elif tag == "script":
            try:
                self.structured.append(json.loads(text))
            except ValueError:
                pass
        elif tag == "p" and len(clean(text)) >= 50:
            self.paragraphs.append(clean(text, 900))
        elif tag == "h1":
            self.meta["heading"] = clean(text, 220)


def dated(text):
    value = parse_date(text)
    if value:
        return value
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return parse_date(text + "T00:00:00Z")
    found = re.search(r"[A-Za-z]{3,9} \d{1,2},? \d{4}", text)
    if found:
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(found[0], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


def article_metadata(page):
    title = page.meta.get("heading") or page.meta.get("og:title", "")
    date = page.meta.get("article:published_time") or page.meta.get("date", "")
    summary = page.meta.get("description") or page.meta.get("og:description", "")
    def read(value):
        nonlocal title, date, summary
        if isinstance(value, list):
            for child in value:
                read(child)
        elif isinstance(value, dict):
            if value.get("datePublished"):
                date = date or value["datePublished"]
                title = title or value.get("headline", "")
                summary = summary or value.get("description", "")
            if "@graph" in value:
                read(value["@graph"])
    for data in page.structured:
        read(data)
    return title, dated(date) or next((d for v in page.dates if (d := dated(v))), None), clean(summary + " " + " ".join(page.paragraphs[:3]), 900)


def fetch_articles(source, fetch, failures=None):
    listing = Page(fetch(source["url"]))
    base = urlsplit(source["url"])
    records, visited = [], set()
    for href, label in listing.links:
        url = urljoin(source["url"], href)
        parsed = urlsplit(url)
        if parsed.hostname != base.hostname or parsed.scheme != "https" or parsed.username or parsed.password or not re.fullmatch(source["article_pattern"], parsed.path) or url in visited:
            continue
        visited.add(url)
        # Listing order is newest first on the configured publisher pages.
        if len(visited) > source.get("scan_limit", 6):
            break
        try:
            page = Page(fetch(url))
        except (OSError, ValueError) as error:
            if failures is not None:
                failures.append(type(error).__name__)
            continue
        title, published, summary = article_metadata(page)
        newsletter_date = re.search(r"/3-2-1/([a-z]+)-(\d+)-(\d{4})$", parsed.path)
        if not published and newsletter_date:
            published = dated(" ".join(newsletter_date.groups()).title())
        published = published or dated(label)
        record = item(title or label, url, published, summary, source)
        if record:
            record["date_precision"] = "day" if published.hour == published.minute == published.second == 0 else "time"
            records.append(record)
    return records


def fetch_x_excerpts(source, fetch):
    body = fetch(source["url"])
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("XML declarations are not allowed")
    records = []
    for entry in ET.fromstring(body).findall("./channel/item"):
        try:
            secondary_url = canonical_url(entry.findtext("link", ""))
        except ValueError:
            continue
        if urlsplit(secondary_url).hostname != urlsplit(source["url"]).hostname:
            continue
        published = dated(entry.findtext("pubDate", ""))
        content = entry.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")
        for block in re.findall(r"<li\b[^>]*>.*?</li>", content, re.S):
            page = Page(block.encode())
            for url, label in page.links:
                parsed = urlsplit(url)
                match = re.fullmatch(r"/([\w]+)/status/(\d+)/?", parsed.path)
                if parsed.hostname not in {"x.com", "twitter.com", "www.twitter.com"} or not match or match[1].lower() not in source["authors"]:
                    continue
                record = item("@" + match[1] + " — " + clean(block, 120), "https://x.com" + parsed.path, published, block, source)
                if record:
                    record.update({"secondary_url": secondary_url, "evidence_type": "community_excerpt", "heat_verified": False})
                    records.append(record)
    return records
