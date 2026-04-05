#!/usr/bin/env python3
"""Tests for compare.py — field-level comparison between BibTeX and CrossRef."""

import os
import subprocess
import sys

import pytest

import compare as compare_module
from compare import compare_entry

TOOL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "skills", "bibtidy", "tools", "compare.py")


class TestPages:
    def test_different_pages(self):
        entry = {"key": "X", "pages": "7262--7272"}
        cr = {"pages": "7242-7252"}
        ms = compare_entry(entry, cr)
        fields = {m["field"] for m in ms}
        assert "pages" in fields

    def test_same_pages_different_hyphens(self):
        """Double vs single hyphen with same numbers should match."""
        entry = {"key": "X", "pages": "100--200"}
        cr = {"pages": "100-200"}
        assert compare_entry(entry, cr) == []

    def test_missing_bib_pages(self):
        """Missing pages not flagged — some venues intentionally omit them."""
        entry = {"key": "X"}
        cr = {"pages": "695-709"}
        ms = compare_entry(entry, cr)
        assert not any(m["field"] == "pages" for m in ms)

    def test_missing_crossref_pages(self):
        """If CrossRef has no pages, don't flag."""
        entry = {"key": "X", "pages": "1--10"}
        cr = {}
        assert compare_entry(entry, cr) == []


class TestTitle:
    def test_same_title_different_case(self):
        entry = {"key": "X", "title": "deep learning for NLP"}
        cr = {"title": "Deep Learning for NLP"}
        assert compare_entry(entry, cr) == []

    def test_same_title_with_braces(self):
        entry = {"key": "X", "title": "{Deep} {Learning} for {NLP}"}
        cr = {"title": "Deep Learning for NLP"}
        assert compare_entry(entry, cr) == []

    def test_different_title(self):
        entry = {"key": "X", "title": "Medical Diffusion -- old title"}
        cr = {"title": "Denoising Diffusion -- new title"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "title" for m in ms)


class TestAuthors:
    def test_matching_authors(self):
        entry = {"key": "X", "author": "Smith, John and Doe, Jane"}
        cr = {"authors": ["Smith, John", "Doe, Jane"]}
        ms = compare_entry(entry, cr)
        assert not any(m["field"] == "author" for m in ms)

    def test_swapped_author_order(self):
        """First-author swap should be flagged."""
        entry = {"key": "X", "author": "Doe, Jane and Smith, John"}
        cr = {"authors": ["Smith, John", "Doe, Jane"]}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "author" for m in ms)

    def test_bib_has_others(self):
        """'and others' with full list available should be flagged for agent review."""
        entry = {"key": "X", "author": "Smith, John and others"}
        cr = {"authors": ["Smith, John", "Doe, Jane", "Lee, Bob"]}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "author" for m in ms)

    def test_bib_has_others_wrong_order(self):
        """'and others' with wrong prefix order should be flagged."""
        entry = {"key": "X", "author": "Doe, Jane and Smith, John and others"}
        cr = {"authors": ["Smith, John", "Doe, Jane", "Lee, Bob"]}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "author" for m in ms)

    def test_bib_has_more_authors_than_crossref(self):
        """Bib with more authors than CrossRef should be flagged for agent review."""
        entry = {"key": "X", "author": "Smith, John and Doe, Jane and Lee, Bob"}
        cr = {"authors": ["Smith, John", "Doe, Jane"]}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "author" for m in ms)

    def test_bib_has_more_but_wrong_prefix(self):
        """Bib with more authors should be flagged if the shared prefix disagrees."""
        entry = {"key": "X", "author": "Doe, Jane and Smith, John and Lee, Bob"}
        cr = {"authors": ["Smith, John", "Doe, Jane"]}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "author" for m in ms)

    def test_bib_missing_authors_no_others(self):
        """Bib with fewer authors and no 'others' should be flagged."""
        entry = {"key": "X", "author": "Smith, John"}
        cr = {"authors": ["Smith, John", "Doe, Jane", "Lee, Bob"]}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "author" for m in ms)

    def test_multiline_authors_match(self):
        """Wrapped author fields should parse the same as single-line fields."""
        entry = {"key": "X", "author": "Alpha, Alice and\n Beta, Bob"}
        cr = {"authors": ["Alpha, Alice", "Beta, Bob"]}
        ms = compare_entry(entry, cr)
        assert not any(m["field"] == "author" for m in ms)


class TestYear:
    def test_different_year(self):
        entry = {"key": "X", "year": "2022"}
        cr = {"year": "2023"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "year" for m in ms)

    def test_same_year(self):
        entry = {"key": "X", "year": "2023"}
        cr = {"year": "2023"}
        assert compare_entry(entry, cr) == []


class TestDOI:
    def test_url_prefix_stripped(self):
        """DOI with https://doi.org/ prefix should match bare DOI."""
        entry = {"key": "X", "doi": "https://doi.org/10.1234/test"}
        cr = {"doi": "10.1234/test"}
        ms = compare_entry(entry, cr)
        assert not any(m["field"] == "doi" for m in ms)

    def test_different_doi(self):
        entry = {"key": "X", "doi": "10.1234/aaa"}
        cr = {"doi": "10.1234/bbb"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "doi" for m in ms)

    def test_missing_bib_doi_not_flagged(self):
        """Missing DOI in bib should not be flagged — don't add new DOIs."""
        entry = {"key": "X"}
        cr = {"doi": "10.1234/test"}
        ms = compare_entry(entry, cr)
        assert not any(m["field"] == "doi" for m in ms)

    def test_legacy_dx_doi_prefix_stripped(self):
        """Legacy dx.doi.org URLs should match bare DOIs."""
        entry = {"key": "X", "doi": "https://dx.doi.org/10.1234/test"}
        cr = {"doi": "10.1234/test"}
        ms = compare_entry(entry, cr)
        assert not any(m["field"] == "doi" for m in ms)


class TestLookupAndCompare:
    def test_legacy_dx_doi_prefix_stripped_before_lookup(self, monkeypatch):
        seen = {}

        def fake_fetch_doi(doi, timeout=10):
            seen["doi"] = doi
            return {"title": "Test Paper", "doi": doi, "url": f"https://doi.org/{doi}"}

        monkeypatch.setattr(compare_module, "search_title", lambda title, rows=3, timeout=10: {"results": []})
        monkeypatch.setattr(compare_module, "fetch_doi", fake_fetch_doi)
        result = compare_module.lookup_and_compare(
            {"key": "X", "title": "Test Paper", "doi": "https://dx.doi.org/10.1234/test"}
        )
        assert seen["doi"] == "10.1234/test"
        assert result["error"] is None

    def test_last_crossref_error_preserved_when_all_strategies_fail(self, monkeypatch):
        monkeypatch.setattr(compare_module, "search_title", lambda title, rows=3, timeout=10: {"results": []})
        monkeypatch.setattr(compare_module, "fetch_doi", lambda doi, timeout=10: {"error": "DOI lookup failed"})
        monkeypatch.setattr(
            compare_module,
            "search_bibliographic",
            lambda title, rows=3, timeout=10: {"error": "Bibliographic search failed"},
        )

        result = compare_module.lookup_and_compare(
            {"key": "X", "title": "Attention Is All You Need", "doi": "10.1234/x"}
        )
        assert result["error"] == "DOI lookup failed"

    def test_bad_doi_returned_alongside_title_match(self, monkeypatch):
        """A resolving DOI that points to a different paper is still returned for agent judgment."""
        correct = {"title": "Real Paper", "authors": ["Smith, John"], "year": "2023", "doi": "10.1234/real"}
        wrong = {"title": "Wrong Paper", "authors": ["Doe, Jane"], "year": "2020", "doi": "10.1234/wrong"}

        monkeypatch.setattr(compare_module, "search_title", lambda title, rows=3, timeout=10: {"results": [correct]})
        monkeypatch.setattr(compare_module, "fetch_doi", lambda doi, timeout=10: wrong)

        entry = {"key": "X", "title": "Real Paper", "author": "Smith, John", "doi": "10.1234/wrong"}
        result = compare_module.lookup_and_compare(entry)
        assert result["error"] is None
        dois = {v["doi"] for v in result["versions"]}
        assert "10.1234/real" in dois
        assert "10.1234/wrong" in dois

    def test_good_doi_supplements_title_match(self, monkeypatch):
        """A DOI that resolves to the same title should be included alongside title results."""
        title_result = {"title": "Real Paper", "authors": ["Smith, John"], "year": "2023", "doi": "10.1234/real"}
        doi_result = {"title": "Real Paper", "authors": ["Smith, John"], "year": "2023", "doi": "10.1234/real"}

        monkeypatch.setattr(
            compare_module, "search_title", lambda title, rows=3, timeout=10: {"results": [title_result]}
        )
        monkeypatch.setattr(compare_module, "fetch_doi", lambda doi, timeout=10: doi_result)

        entry = {"key": "X", "title": "Real Paper", "author": "Smith, John", "doi": "10.1234/real"}
        result = compare_module.lookup_and_compare(entry)
        assert result["error"] is None
        # Same DOI, so should deduplicate to 1 version
        assert len(result["versions"]) == 1

    def test_bibliographic_search_deduplicates_with_title_match(self, monkeypatch):
        """Both title and bibliographic searches run; results are deduplicated by DOI."""
        monkeypatch.setattr(
            compare_module,
            "search_title",
            lambda title, rows=3, timeout=10: {"results": [{"title": "Real Paper", "doi": "10.1234/real"}]},
        )
        monkeypatch.setattr(
            compare_module,
            "search_bibliographic",
            lambda title, rows=3, timeout=10: {"results": [{"title": "Real Paper", "doi": "10.1234/real"}]},
        )
        monkeypatch.setattr(compare_module, "fetch_doi", lambda doi, timeout=10: {"error": "DOI lookup failed"})

        result = compare_module.lookup_and_compare({"key": "X", "title": "Real Paper", "doi": "10.1234/wrong"})
        assert result["error"] is None
        assert len(result["versions"]) == 1

    def test_doi_only_entry_no_title(self, monkeypatch):
        """Entry with DOI but no title should still attempt DOI lookup."""
        doi_result = {"title": "Found Paper", "doi": "10.1234/x", "url": "https://doi.org/10.1234/x"}
        monkeypatch.setattr(compare_module, "fetch_doi", lambda doi, timeout=10: doi_result)
        result = compare_module.lookup_and_compare({"key": "X", "doi": "10.1234/x"})
        assert result["error"] is None
        assert len(result["versions"]) == 1

    def test_title_search_error_preserved_without_doi(self, monkeypatch):
        monkeypatch.setattr(compare_module, "search_title", lambda title, rows=3, timeout=10: {"error": "Rate limited"})
        monkeypatch.setattr(compare_module, "search_bibliographic", lambda title, rows=3, timeout=10: {"results": []})

        result = compare_module.lookup_and_compare({"key": "X", "title": "Attention Is All You Need"})
        assert result["error"] == "Rate limited"


class TestVenue:
    @pytest.mark.parametrize(
        "preprint,published",
        [("arXiv preprint arXiv:2210.02747", "Nature"), ("bioRxiv", "Nature"), ("medRxiv", "The Lancet")],
    )
    def test_preprint_to_journal(self, preprint, published):
        entry = {"key": "X", "journal": preprint}
        cr = {"journal": published}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "journal" for m in ms)

    def test_same_journal(self):
        """Same journal name should not flag."""
        entry = {"key": "X", "journal": "Nature"}
        cr = {"journal": "Nature"}
        assert compare_entry(entry, cr) == []

    def test_wrong_nonpreprint_journal(self):
        """Wrong non-preprint journal should be flagged for review."""
        entry = {"key": "X", "journal": "ICML"}
        cr = {"journal": "NeurIPS"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "journal" for m in ms)

    def test_similar_nonpreprint_journal(self):
        """Case/brace differences in same journal should not flag."""
        entry = {"key": "X", "journal": "{Nature} Methods"}
        cr = {"journal": "Nature Methods"}
        assert compare_entry(entry, cr) == []


class TestNumber:
    def test_different_number(self):
        entry = {"key": "X", "number": "4"}
        cr = {"number": "24"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "number" for m in ms)

    def test_missing_bib_number(self):
        entry = {"key": "X"}
        cr = {"number": "24"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "number" for m in ms)

    def test_same_number(self):
        entry = {"key": "X", "number": "24"}
        cr = {"number": "24"}
        assert compare_entry(entry, cr) == []

    def test_missing_crossref_number(self):
        """If CrossRef has no number, don't flag."""
        entry = {"key": "X", "number": "4"}
        cr = {}
        assert compare_entry(entry, cr) == []


class TestVolume:
    def test_different_volume(self):
        entry = {"key": "X", "volume": "30"}
        cr = {"volume": "33"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "volume" for m in ms)

    def test_missing_bib_volume(self):
        entry = {"key": "X"}
        cr = {"volume": "13"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "volume" for m in ms)

    def test_same_volume(self):
        entry = {"key": "X", "volume": "30"}
        cr = {"volume": "30"}
        assert compare_entry(entry, cr) == []


class TestEntryType:
    def test_type_mismatch(self):
        entry = {"key": "X", "entry_type": "article"}
        cr = {"type": "inproceedings"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "entry_type" for m in ms)

    def test_type_match(self):
        entry = {"key": "X", "entry_type": "article"}
        cr = {"type": "article"}
        assert compare_entry(entry, cr) == []


class TestBootitleVsJournal:
    def test_booktitle_field_preserved(self):
        """Venue mismatch for @inproceedings should use 'booktitle' so the agent edits the right field."""
        entry = {
            "key": "X",
            "entry_type": "inproceedings",
            "booktitle": "Proceedings of the IEEE/CVF international conference on computer vision",
        }
        cr = {"journal": "2021 IEEE/CVF International Conference on Computer Vision (ICCV)"}
        ms = compare_entry(entry, cr)
        venue_ms = [m for m in ms if m["field"] in ("journal", "booktitle")]
        for m in venue_ms:
            assert m["field"] == "booktitle", "Should use 'booktitle' not 'journal'"

    def test_journal_field_preserved(self):
        """Venue mismatch for @article should use 'journal' so the agent edits the right field."""
        entry = {"key": "X", "entry_type": "article", "journal": "arXiv preprint arXiv:2210.02747"}
        cr = {"journal": "Nature"}
        ms = compare_entry(entry, cr)
        venue_ms = [m for m in ms if m["field"] in ("journal", "booktitle")]
        assert len(venue_ms) == 1
        assert venue_ms[0]["field"] == "journal"

    def test_missing_booktitle_uses_booktitle_field(self):
        """Missing conference venue should still be written to booktitle."""
        entry = {"key": "X", "entry_type": "inproceedings", "title": "A Great Paper"}
        cr = {"title": "A Great Paper", "journal": "International Conference on Learning Representations"}
        ms = compare_entry(entry, cr)
        venue_ms = [m for m in ms if m["field"] in ("journal", "booktitle")]
        assert len(venue_ms) == 1
        assert venue_ms[0]["field"] == "booktitle"


class TestMissingFields:
    def test_missing_title_flagged(self):
        """Entry with no title should be flagged when CrossRef has one."""
        entry = {"key": "X", "author": "Smith, John", "year": "2023"}
        cr = {"title": "A Great Paper", "authors": ["Smith, John"], "year": "2023"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "title" for m in ms)

    def test_missing_author_flagged(self):
        """Entry with no author should be flagged when CrossRef has authors."""
        entry = {"key": "X", "title": "A Great Paper", "year": "2023"}
        cr = {"title": "A Great Paper", "authors": ["Smith, John"], "year": "2023"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "author" for m in ms)

    def test_missing_year_flagged(self):
        """Entry with no year should be flagged when CrossRef has one."""
        entry = {"key": "X", "title": "A Great Paper"}
        cr = {"title": "A Great Paper", "year": "2023"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "year" for m in ms)

    def test_missing_venue_flagged(self):
        """Entry with no journal/booktitle should be flagged when CrossRef has one."""
        entry = {"key": "X", "title": "A Great Paper"}
        cr = {"title": "A Great Paper", "journal": "Nature"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "journal" for m in ms)


class TestDOICaseInsensitive:
    @pytest.mark.parametrize("prefix", ["HTTPS://DOI.ORG/", "Http://Doi.Org/", "https://DX.DOI.ORG/"])
    def test_mixed_case_doi_url(self, prefix):
        """Mixed-case DOI URL prefixes should still be stripped."""
        entry = {"key": "X", "doi": f"{prefix}10.1234/test"}
        cr = {"doi": "10.1234/test"}
        ms = compare_entry(entry, cr)
        assert not any(m["field"] == "doi" for m in ms)


class TestCombined:
    def test_strudel_case(self):
        """The exact case that failed: subtle page number difference."""
        entry = {
            "key": "strudel2021segmenter",
            "entry_type": "inproceedings",
            "title": "Segmenter: Transformer for semantic segmentation",
            "author": "Strudel, Robin and Garcia, Ricardo and Laptev, Ivan and Schmid, Cordelia",
            "booktitle": "Proceedings of the IEEE/CVF international conference on computer vision",
            "pages": "7262--7272",
            "year": "2021",
        }
        cr = {
            "title": "Segmenter: Transformer for Semantic Segmentation",
            "authors": ["Strudel, Robin", "Garcia, Ricardo", "Laptev, Ivan", "Schmid, Cordelia"],
            "year": "2021",
            "journal": "2021 IEEE/CVF International Conference on Computer Vision (ICCV)",
            "pages": "7242-7252",
            "doi": "10.1109/iccv48922.2021.00717",
            "type": "inproceedings",
            "url": "https://doi.org/10.1109/iccv48922.2021.00717",
        }
        ms = compare_entry(entry, cr)
        fields = {m["field"] for m in ms}
        assert "pages" in fields, "Must catch the 7262→7242 page difference"

    def test_correct_entry_no_mismatches(self):
        """A correct entry should produce no mismatches."""
        entry = {
            "key": "vaswani2017attention",
            "entry_type": "inproceedings",
            "title": "Attention is All you Need",
            "author": "Vaswani, Ashish and Shazeer, Noam",
            "booktitle": "Advances in Neural Information Processing Systems",
            "volume": "30",
            "year": "2017",
        }
        cr = {
            "title": "Attention Is All You Need",
            "authors": ["Vaswani, Ashish", "Shazeer, Noam"],
            "year": "2017",
            "volume": "30",
            "type": "inproceedings",
        }
        assert compare_entry(entry, cr) == []


class TestCLI:
    def test_parenthesized_entry_rejected(self, tmp_path):
        bib = tmp_path / "paren.bib"
        bib.write_text("@article(ParenKey, title={Hello}, year={2020})\n")
        result = subprocess.run([sys.executable, TOOL_PATH, str(bib)], capture_output=True, text=True)
        assert result.returncode == 1
        assert "not supported" in result.stderr
