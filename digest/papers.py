"""Search PubMed across journals and retain dated original research abstracts."""
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import timedelta
from urllib.parse import urlencode

from .collect import clean, item, parse_date

_LOCK = threading.Lock()
_NEXT_REQUEST = 0.0


def request(fetch, url):
    global _NEXT_REQUEST
    # NCBI permits three requests/second without an API key; all paper sources share this limiter.
    with _LOCK:
        time.sleep(max(0, _NEXT_REQUEST - time.monotonic()))
        _NEXT_REQUEST = time.monotonic() + 0.36
        return fetch(url)


def parse_papers(body, source):
    if b"<!ENTITY" in body.upper():
        raise ValueError("XML entities are not allowed")
    # PubMed's declared external DTD is metadata only; ElementTree never fetches it.
    body = re.sub(rb'<!DOCTYPE PubmedArticleSet PUBLIC "[^"]+" "https://dtd\.nlm\.nih\.gov/[^"<>]+">', b'', body)
    if b"<!DOCTYPE" in body.upper():
        raise ValueError("Unknown XML declarations are not allowed")
    records = []
    for paper in ET.fromstring(body).findall("PubmedArticle"):
        article = paper.find("MedlineCitation/Article")
        pmid = paper.findtext("MedlineCitation/PMID", "")
        if article is None or not pmid.isdigit():
            continue
        types = [clean("".join(v.itertext())) for v in article.findall("PublicationTypeList/PublicationType")]
        if any("retract" in t.lower() or "expression of concern" in t.lower() or "published erratum" in t.lower() for t in types):
            continue
        if any("retract" in v.get("RefType", "").lower() for v in paper.findall("MedlineCitation/CommentsCorrectionsList/CommentsCorrections")):
            continue
        dates = []
        for date in article.findall("ArticleDate") + article.findall("Journal/JournalIssue/PubDate"):
            year, month, day = (date.findtext(field, "") for field in ("Year", "Month", "Day"))
            if year.isdigit() and month.isdigit() and day.isdigit():
                value = parse_date(year + "-" + month.zfill(2) + "-" + day.zfill(2) + "T00:00:00Z")
                if value:
                    dates.append(value)
        sections = article.findall("Abstract/AbstractText")
        if not dates or not sections:
            continue
        # Preserve conclusion and methods, rather than only a long background paragraph.
        ordered = sorted(sections, key=lambda s: (0 if s.get("NlmCategory", "").upper() == "CONCLUSIONS" else 1 if s.get("NlmCategory", "").upper() == "METHODS" else 2))
        excerpts = []
        for section in ordered[:3]:
            text = clean("".join(section.itertext()), 10000)
            label = section.get("Label") or section.get("NlmCategory") or "Abstract"
            if len(sections) == 1 and len(text) > 550:
                label += " excerpt (opening/end)"
                text = text[:180] + " ... " + text[-350:]
            excerpts.append(label + ": " + text[:400] if len(sections) > 1 else label + ": " + text)
        abstract = " ".join(excerpts)
        subjects = [v.findtext("DescriptorName", "") for v in paper.findall("MedlineCitation/MeshHeadingList/MeshHeading")]
        journal = clean(article.findtext("Journal/Title", "未说明期刊"), 220)
        evidence = "Publication types: " + ", ".join(types) + "; subjects: " + ", ".join(s for s in subjects if s in {"Humans", "Animals"})
        title_node = article.find("ArticleTitle")
        record = item("".join(title_node.itertext()) if title_node is not None else "", "https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/", min(dates), abstract, source)
        if record:
            record.update({"summary": clean(evidence + "; " + abstract, 1100), "publisher": journal,
                           "evidence_type": "research_abstract", "publication_types": types, "date_precision": "day",
                           "discovery": "topic_search", "discovery_query": source["query"]})
            records.append(record)
    return records


def fetch_papers(source, now, fetch):
    params = {"db": "pubmed", "term": source["query"], "retmode": "json", "sort": "pub_date",
              "retmax": source.get("scan_limit", 8), "datetype": "pdat",
              "mindate": (now - timedelta(hours=source["window_hours"])).strftime("%Y/%m/%d"), "maxdate": now.strftime("%Y/%m/%d")}
    ids = json.loads(request(fetch, source["url"] + "esearch.fcgi?" + urlencode(params)))["esearchresult"]["idlist"]
    if not ids:
        return []
    if any(not isinstance(pmid, str) or not pmid.isdigit() for pmid in ids):
        raise ValueError("Invalid paper identifiers")
    body = request(fetch, source["url"] + "efetch.fcgi?" + urlencode({"db": "pubmed", "retmode": "xml", "id": ",".join(ids)}))
    return parse_papers(body, source)
