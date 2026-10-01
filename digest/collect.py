"""Bounded public feed collection; no full articles, transcripts or login cookies."""
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

MAX_DOWNLOAD = 3_000_000
AI_WORDS = re.compile(r"\b(ai|llm|gpt|claude|gemini|deepseek|openai|anthropic|agent|agents|ollama|vllm|transformers|qwen|llama|hugging)\b|人工智能|大模型", re.I)


def download(url, timeout=18):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Only HTTPS sources are allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Daily-Digest/1.0", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_DOWNLOAD + 1)
    if len(body) > MAX_DOWNLOAD:
        raise ValueError("Source exceeded download limit")
    return body


def clean(text, limit=450):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()[:limit]


def canonical_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Invalid public article URL")
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, urllib.parse.urlencode(query), ""))


def parse_date(value):
    try:
        date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError, IndexError):
            return None
    # Undated or timezone-less entries are not treated as fresh news.
    return date.astimezone(timezone.utc) if date.tzinfo else None


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def item(title, url, published, summary, source):
    url = canonical_url(url)
    title = clean(title, 220)
    if not title or published is None:
        return None
    # Identical version numbers in different repositories are different events.
    title_key = fingerprint((source["name"] if source["kind"] == "github" else "") + re.sub(r"[^\w]+", "", title.casefold()))
    return {"title": title, "url": url, "published": published.isoformat(), "summary": clean(summary),
            "source": source["name"], "kind": source["kind"], "keys": ["url:" + fingerprint(url), "title:" + title_key]}


def parse_feed(body, source):
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("XML declarations are not allowed")
    root = ET.fromstring(body)
    records = []
    for entry in root.findall("./channel/item") + root.findall("./{http://www.w3.org/2005/Atom}entry"):
        fields = {node.tag.split("}")[-1]: node for node in entry}
        def value(name):
            node = fields.get(name)
            return "" if node is None else "".join(node.itertext())
        links = [node for node in entry if node.tag.split("}")[-1] == "link"]
        url = next((node.get("href") for node in links if node.get("href") and node.get("rel", "alternate") == "alternate"), value("link"))
        published = parse_date(value("published") or value("pubDate") or value("date") or value("updated"))
        try:
            record = item(value("title"), url, published, value("description") or value("summary") or value("content"), source)
        except ValueError:
            continue
        if record:
            records.append(record)
    return records


def fetch_source(source, now, window_hours, fetch=download):
    url = source["url"]
    if source["kind"] == "hn":
        query = urllib.parse.urlencode({"tags": "story", "query": "AI", "hitsPerPage": 50,
                                       "numericFilters": "created_at_i>" + str(int((now - timedelta(hours=window_hours)).timestamp()))})
        raw = json.loads(fetch(url + "?" + query))["hits"]
        records = []
        for hit in raw:
            try:
                record = item(hit.get("title"), hit.get("url") or "https://news.ycombinator.com/item?id=" + hit["objectID"],
                              parse_date(hit.get("created_at")), "HN discussion; points: " + str(hit.get("points", 0)), source)
            except (ValueError, KeyError):
                continue
            if record and AI_WORDS.search(record["title"]):
                records.append(record)
    else:
        records = parse_feed(fetch(url), source)
    cutoff = now - timedelta(hours=window_hours)
    fresh = [r for r in records if cutoff <= parse_date(r["published"]) <= now + timedelta(minutes=5)
             and (not source.get("ai_filter") or AI_WORDS.search(r["title"] + " " + r["summary"]))]
    fresh.sort(key=lambda r: r["published"], reverse=True)
    return fresh[:source.get("limit", 6)], {"source": source["name"], "kind": source["kind"], "status": "ok", "raw": len(records), "fresh": len(fresh)}


def collect(config, now=None, sent_keys=(), fetch=download):
    now = now or datetime.now(timezone.utc)
    sources = [s for s in config["sources"] if s.get("enabled", True)]
    def read(source):
        try:
            return fetch_source(source, now, config["window_hours"], fetch)
        except Exception as error:
            return [], {"source": source["name"], "kind": source["kind"], "status": "failed", "error": type(error).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read, sources))
    # Round-robin preserves source diversity under the bounded prompt size.
    seen = set(sent_keys)
    candidates = []
    queues = [list(records) for records, _ in results]
    while any(queues) and len(candidates) < config["max_candidates"]:
        for queue in queues:
            if not queue or len(candidates) >= config["max_candidates"]:
                continue
            record = queue.pop(0)
            if any(key in seen for key in record["keys"]):
                continue
            seen.update(record["keys"])
            record["id"] = "C" + str(len(candidates) + 1).zfill(3)
            candidates.append(record)
    return candidates, [report for _, report in results]
