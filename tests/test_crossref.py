#!/usr/bin/env python3
"""Tests for crossref.py — JSON parsing/formatting and error handling."""

import json
import urllib.error
from unittest.mock import patch

import crossref

SAMPLE_WORK_ITEM = {
    "DOI": "10.1234/example.2024",
    "URL": "https://doi.org/10.1234/example.2024",
    "type": "journal-article",
    "title": ["Attention Is All You Need"],
    "author": [{"family": "Vaswani", "given": "Ashish"}, {"family": "Shazeer", "given": "Noam"}],
    "container-title": ["Advances in Neural Information Processing Systems"],
    "volume": "30",
    "issue": "1",
    "page": "5998-6008",
    "published-print": {"date-parts": [[2017, 6, 12]]},
}

SAMPLE_WORK_MINIMAL = {"DOI": "10.9999/minimal", "type": "book", "title": ["A Minimal Entry"]}

SAMPLE_SEARCH_RESPONSE = {"message": {"items": [SAMPLE_WORK_ITEM, SAMPLE_WORK_MINIMAL]}}

SAMPLE_DOI_RESPONSE = {"message": SAMPLE_WORK_ITEM}

EXPECTED_FIELDS = {"title", "authors", "year", "journal", "volume", "number", "pages", "doi", "type", "url"}


class TestFormatWork:
    def test_full_item(self):
        result = crossref.format_work(SAMPLE_WORK_ITEM)
        assert result["title"] == "Attention Is All You Need"
        assert result["authors"] == ["Vaswani, Ashish", "Shazeer, Noam"]
        assert result["year"] == "2017"
        assert result["journal"] == "Advances in Neural Information Processing Systems"
        assert result["volume"] == "30"
        assert result["number"] == "1"
        assert result["pages"] == "5998-6008"
        assert result["doi"] == "10.1234/example.2024"
        assert result["type"] == "article"
        assert result["url"] == "https://doi.org/10.1234/example.2024"

    def test_minimal_item(self):
        result = crossref.format_work(SAMPLE_WORK_MINIMAL)
        assert result["title"] == "A Minimal Entry"
        assert result["authors"] == []
        assert result["year"] is None
        assert result["journal"] is None
        assert result["volume"] is None
        assert result["number"] is None
        assert result["pages"] is None
        assert result["type"] == "book"

    def test_empty_item(self):
        result = crossref.format_work({})
        assert result["title"] is None
        assert result["authors"] == []
        assert result["year"] is None

    def test_author_family_only(self):
        result = crossref.format_work({"author": [{"family": "Turing"}]})
        assert result["authors"] == ["Turing"]

    def test_author_given_only(self):
        result = crossref.format_work({"author": [{"given": "Alan"}]})
        assert result["authors"] == ["Alan"]


class TestExtractYear:
    def test_published_print(self):
        assert crossref._extract_year({"published-print": {"date-parts": [[2020, 3, 15]]}}) == "2020"

    def test_issued_fallback(self):
        assert crossref._extract_year({"issued": {"date-parts": [[2019]]}}) == "2019"

    def test_no_date(self):
        assert crossref._extract_year({}) is None

    def test_empty_date_parts(self):
        assert crossref._extract_year({"published-print": {"date-parts": [[]]}}) is None


class TestMapType:
    def test_known_types(self):
        assert crossref._map_type("journal-article") == "article"
        assert crossref._map_type("proceedings-article") == "inproceedings"
        assert crossref._map_type("book") == "book"
        assert crossref._map_type("dissertation") == "phdthesis"

    def test_unknown_type_passthrough(self):
        assert crossref._map_type("something-new") == "something-new"


class TestFetchDoi:
    @patch("crossref._fetch_json")
    def test_success(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_DOI_RESPONSE
        result = crossref.fetch_doi("10.1234/example.2024")
        assert result["title"] == "Attention Is All You Need"
        assert result["doi"] == "10.1234/example.2024"
        assert "error" not in result

    @patch("crossref._fetch_json")
    def test_404(self, mock_fetch):
        mock_fetch.side_effect = urllib.error.HTTPError(url="x", code=404, msg="Not Found", hdrs={}, fp=None)
        result = crossref.fetch_doi("10.0000/nope")
        assert "not found" in result["error"].lower()

    @patch("crossref._fetch_json")
    def test_429_rate_limit(self, mock_fetch):
        mock_fetch.side_effect = urllib.error.HTTPError(url="x", code=429, msg="Too Many Requests", hdrs={}, fp=None)
        result = crossref.fetch_doi("10.1234/x")
        assert "rate limit" in result["error"].lower()

    @patch("crossref._fetch_json")
    def test_timeout(self, mock_fetch):
        mock_fetch.side_effect = urllib.error.URLError("timed out")
        result = crossref.fetch_doi("10.1234/x", timeout=5)
        assert "timed out" in result["error"].lower()

    @patch("crossref._fetch_json")
    def test_network_error(self, mock_fetch):
        mock_fetch.side_effect = urllib.error.URLError("Name or service not known")
        result = crossref.fetch_doi("10.1234/x")
        assert "network error" in result["error"].lower()

    @patch("crossref._fetch_json")
    def test_malformed_json(self, mock_fetch):
        mock_fetch.return_value = {"unexpected": "structure"}
        result = crossref.fetch_doi("10.1234/x")
        assert "malformed" in result["error"].lower()

    @patch("crossref._fetch_json")
    def test_timeout_error_exception(self, mock_fetch):
        mock_fetch.side_effect = TimeoutError("connection timed out")
        result = crossref.fetch_doi("10.1234/x", timeout=3)
        assert "timed out" in result["error"].lower()


class TestSearchTitle:
    @patch("crossref._fetch_json")
    def test_success(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_SEARCH_RESPONSE
        result = crossref.search_title("Attention Is All You Need")
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Attention Is All You Need"
        assert result["results"][1]["title"] == "A Minimal Entry"

    @patch("crossref._fetch_json")
    def test_empty_results(self, mock_fetch):
        mock_fetch.return_value = {"message": {"items": []}}
        result = crossref.search_title("nonexistent paper xyz")
        assert result["results"] == []

    @patch("crossref._fetch_json")
    def test_http_error(self, mock_fetch):
        mock_fetch.side_effect = urllib.error.HTTPError(
            url="x", code=500, msg="Internal Server Error", hdrs={}, fp=None
        )
        result = crossref.search_title("test")
        assert "error" in result

    @patch("crossref._fetch_json")
    def test_timeout(self, mock_fetch):
        mock_fetch.side_effect = urllib.error.URLError("timed out")
        result = crossref.search_title("test", timeout=2)
        assert "timed out" in result["error"].lower()

    @patch("crossref._fetch_json")
    def test_malformed_response(self, mock_fetch):
        mock_fetch.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        result = crossref.search_title("test")
        assert "malformed" in result["error"].lower()


class TestOutputFormat:
    def test_all_fields_present(self):
        result = crossref.format_work(SAMPLE_WORK_ITEM)
        assert set(result.keys()) == EXPECTED_FIELDS

    def test_json_serializable(self):
        result = crossref.format_work(SAMPLE_WORK_ITEM)
        assert json.loads(json.dumps(result)) == result

    def test_error_json_serializable(self):
        error_result = {"error": "Something went wrong"}
        assert "error" in json.loads(json.dumps(error_result))
