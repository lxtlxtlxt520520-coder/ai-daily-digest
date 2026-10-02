"""Discover different publishers by topic, then read dated public originals."""
import json
import re
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

from .collect import clean, item
from .pages import Page, article_metadata


def daily_queries(source, now):
    queries = source.get("queries", [source.get("query", "")])
    offset = now.astimezone(ZoneInfo("Asia/Shanghai")).date().toordinal() % len(queries)
    return [queries[(offset + i) % len(queries)] for i in range(min(source.get("queries_per_run", 2), len(queries)))]


def fetch_discussions(source, now, fetch, failures):
    queues = []
    cutoff = now - timedelta(hours=source["window_hours"])
    for query in daily_queries(source, now):
        params = {"tags": "story", "query": query, "hitsPerPage": 20,
                  "numericFilters": "created_at_i>" + str(int(cutoff.timestamp())) + ",points>=" + str(source.get("min_points", 15))}
        try:
            hits = json.loads(fetch(source["url"] + "?" + urlencode(params)))["hits"]
            queues.append([(hit, query) for hit in hits])
        except (OSError, ValueError, KeyError) as error:
            failures.append(type(error).__name__)
    selected, seen = [], set()
    while any(queues) and len(selected) < source.get("scan_limit", 6):
        for queue in queues:
            if not queue or len(selected) >= source.get("scan_limit", 6):
                continue
            hit, query = queue.pop(0)
            url, title = hit.get("url") or "", clean(hit.get("title"))
            parts = urlsplit(url)
            text = title + " " + clean(hit.get("story_text"))
            if url in seen or parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.path in {"", "/"}:
                continue
            if source.get("include_pattern") and not re.search(source["include_pattern"], text, re.I):
                continue
            if source.get("exclude_pattern") and re.search(source["exclude_pattern"], text, re.I):
                continue
            seen.add(url)
            selected.append((hit, query))
    records = []
    for hit, query in selected:
        try:
            page = Page(fetch(hit["url"]))
            title, published, excerpt = article_metadata(page)
            # A community submission/search date never proves an article's freshness.
            if published is None or len(excerpt) < 80:
                continue
            record = item(title or hit["title"], hit["url"], published, excerpt, source)
            if record:
                record.update({"publisher": urlsplit(record["url"]).hostname, "discovery": "topic_search",
                               "discovery_query": query, "evidence_type": "original_excerpt",
                               "discussion_points": hit.get("points"),
                               "secondary_url": "https://news.ycombinator.com/item?" + urlencode({"id": hit["objectID"]})})
                records.append(record)
        except (OSError, ValueError, KeyError) as error:
            failures.append(type(error).__name__)
    return records
