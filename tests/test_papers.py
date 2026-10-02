import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from digest.papers import fetch_papers, parse_papers

SOURCE = {"name": "PubMed", "kind": "pubmed_search", "category": "health", "url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
          "query": "sleep AND systematic review[pt]", "window_hours": 720, "scan_limit": 8}
PAPER = '''<PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Sleep <i>review</i></ArticleTitle><Journal><Title>Original Journal</Title><JournalIssue><PubDate><Year>2027</Year><Month>1</Month><Day>1</Day></PubDate></JournalIssue></Journal><ArticleDate DateType="Electronic"><Year>2026</Year><Month>9</Month><Day>21</Day></ArticleDate><PublicationTypeList><PublicationType>Systematic Review</PublicationType></PublicationTypeList><Abstract><AbstractText NlmCategory="BACKGROUND">Background ''' + 'long context ' * 60 + '''</AbstractText><AbstractText NlmCategory="METHODS">Human studies with observational limitations.</AbstractText><AbstractText NlmCategory="CONCLUSIONS">Association found, causal effects remain uncertain.</AbstractText></Abstract></Article><MeshHeadingList><MeshHeading><DescriptorName>Humans</DescriptorName></MeshHeading></MeshHeadingList></MedlineCitation></PubmedArticle>'''


class PaperTests(unittest.TestCase):
    def test_original_abstract_preserves_conclusion_design_and_first_publication(self):
        records = parse_papers(('<PubmedArticleSet>' + PAPER + '</PubmedArticleSet>').encode(), SOURCE)
        self.assertEqual(records[0]["published"][:10], "2026-09-21")
        self.assertEqual(records[0]["title"], "Sleep review")
        self.assertIn("Systematic Review", records[0]["summary"])
        self.assertIn("Humans", records[0]["summary"])
        self.assertIn("causal effects remain uncertain", records[0]["summary"])
        self.assertEqual(records[0]["publisher"], "Original Journal")

    def test_retraction_undated_and_missing_abstract_are_excluded(self):
        retracted = PAPER.replace('Systematic Review', 'Retracted Publication')
        undated = PAPER.replace('<Day>21</Day>', '').replace('<Day>1</Day>', '')
        no_abstract = PAPER.replace('<Abstract>', '<Other>').replace('</Abstract>', '</Other>')
        for article in (retracted, undated, no_abstract):
            self.assertEqual(parse_papers(('<PubmedArticleSet>' + article + '</PubmedArticleSet>').encode(), SOURCE), [])

    def test_ncbi_dtd_is_not_fetched_and_unknown_entities_are_rejected(self):
        header = '<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed.dtd">'
        self.assertEqual(len(parse_papers((header + '<PubmedArticleSet>' + PAPER + '</PubmedArticleSet>').encode(), SOURCE)), 1)
        for body in (b'<!DOCTYPE PubmedArticleSet SYSTEM "https://evil.example/dtd"><PubmedArticleSet/>', b'<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]><PubmedArticleSet/>'):
            with self.assertRaises(ValueError):
                parse_papers(body, SOURCE)

    def test_search_has_a_publication_window_and_no_request_for_zero_matches(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return json.dumps({"esearchresult": {"idlist": []}}).encode()
        with patch("digest.papers.time.sleep"):
            self.assertEqual(fetch_papers(SOURCE, datetime(2026, 10, 2, tzinfo=timezone.utc), fetch), [])
        self.assertEqual(len(calls), 1)
        params = parse_qs(urlsplit(calls[0]).query)
        self.assertEqual(params["datetype"], ["pdat"])
        self.assertEqual(params["maxdate"], ["2026/10/02"])

    def test_long_unstructured_abstract_keeps_the_end_and_labels_excerpt(self):
        paper = PAPER.replace('<Abstract>', '<Other>').replace('</Abstract>', '</Other>')
        paper = paper.replace('</Article>', '<Abstract><AbstractText>' + 'Background context. ' * 80 + 'Important concluding limitation.</AbstractText></Abstract></Article>')
        record = parse_papers(('<PubmedArticleSet>' + paper + '</PubmedArticleSet>').encode(), SOURCE)[0]
        self.assertIn('Important concluding limitation.', record['summary'])
        self.assertIn('opening/end', record['summary'])
