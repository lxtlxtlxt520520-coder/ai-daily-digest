"""Discover public repositories using observed stars and original GitHub metadata."""
import json
import re
from datetime import timedelta
from urllib.parse import quote, urlencode

from .collect import item
from .pages import Page

RELEVANT = re.compile(r"\b(ai|agent|agents|skill|skills|mcp|llm|automation|workflow|knowledge|research)\b", re.I)


def trending_repositories(body):
    repositories = []
    for block in re.findall(r"<article\b[^>]*>.*?</article>", body.decode(errors="replace"), re.S):
        page = Page(block.encode())
        repo = next((href.strip("/") for href, label in page.links if re.fullmatch(r"/[\w.-]+/[\w.-]+", href) and "/sponsors/" not in href), None)
        if not repo:
            continue
        growth = re.search(r"([\d,]+)\s+stars today", re.sub(r"<[^>]+>", " ", block))
        description = " ".join(page.paragraphs)
        if RELEVANT.search(repo + " " + description):
            repositories.append((repo, int(growth[1].replace(",", "")) if growth else None))
    return repositories


def fetch_projects(source, now, fetch, failures=None):
    if source["kind"] == "github_search":
        from .discovery import daily_queries
        queries = daily_queries(source, now) if source.get("queries") else [source.get("query", "")]
        repos = []
        for query in queries:
            url = source["url"]
            if query:
                query += " pushed:>=" + (now - timedelta(days=180)).date().isoformat()
                if source.get("created_days"):
                    query += " created:>=" + (now - timedelta(days=source["created_days"])).date().isoformat()
                url += "?" + urlencode({"q": query, "sort": "stars", "per_page": source.get("scan_limit", 8)})
            try:
                repos.extend((repo, None) for repo in json.loads(fetch(url))["items"])
            except (OSError, ValueError, KeyError) as error:
                if failures is None:
                    raise
                failures.append(type(error).__name__)
    else:
        repos = []
        for name, growth in trending_repositories(fetch(source["url"]))[:source.get("scan_limit", 6)]:
            repo = json.loads(fetch("https://api.github.com/repos/" + quote(name, safe="/")))
            repos.append((repo, growth))
    records = []
    for repo, growth in repos:
        stars = repo.get("stargazers_count", 0)
        if repo.get("archived") or repo.get("fork") or repo.get("disabled") or not RELEVANT.search(repo["full_name"] + " " + (repo.get("description") or "") + " " + " ".join(repo.get("topics", []))):
            continue
        if stars < source.get("min_stars", 1000) and not (stars >= 300 and growth is not None and growth >= 100):
            continue
        license_name = (repo.get("license") or {}).get("spdx_id", "未核实")
        evidence = (repo.get("description") or "") + "; total stars: " + str(stars)
        if growth is not None:
            evidence += "; GitHub Trending stars today: " + str(growth)
        evidence += "; pushed_at: " + str(repo.get("pushed_at")) + "; language: " + str(repo.get("language")) + "; license: " + license_name
        record = item(repo["full_name"], repo["html_url"], now, evidence, source)
        if record:
            record.update({"observed_at": now.isoformat(), "date_precision": "observed", "stars": stars, "stars_today": growth,
                           "pushed_at": repo.get("pushed_at"), "license": license_name,
                           "discovery": "topic_search" if source["kind"] == "github_search" else "trending"})
            records.append(record)
    records.sort(key=lambda r: (r["stars_today"] or 0, r["stars"]), reverse=True)
    return records
