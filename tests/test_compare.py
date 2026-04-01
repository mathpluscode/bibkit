#!/usr/bin/env python3
"""Tests for compare.py — field-level comparison between BibTeX and CrossRef."""

from compare import compare_entry


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
    def test_bib_has_more_authors_than_crossref_is_ok(self):
        """Bib with more authors is OK — CrossRef may truncate."""
        entry = {"key": "X", "author": "Smith, John and Dayan, Peter"}
        cr = {"authors": ["Smith, John"]}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "author" for m in ms)

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
        """'and others' with full list available should be flagged for Claude to decide."""
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
        """Bib with more authors than CrossRef should be flagged for Claude to decide."""
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

    def test_missing_bib_doi(self):
        entry = {"key": "X"}
        cr = {"doi": "10.1234/test"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "doi" and m["severity"] == "review" for m in ms)


class TestVenue:
    def test_arxiv_to_journal(self):
        entry = {"key": "X", "journal": "arXiv preprint arXiv:2210.02747"}
        cr = {"journal": "Nature"}
        ms = compare_entry(entry, cr)
        assert any(m["field"] == "journal" for m in ms)

    def test_biorxiv_to_journal(self):
        entry = {"key": "X", "journal": "bioRxiv"}
        cr = {"journal": "Nature"}
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
        assert any(m["field"] == "journal" and m["severity"] == "review" for m in ms)

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
        """Venue mismatch for @inproceedings should use 'booktitle' so Claude edits the right field."""
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
        """Venue mismatch for @article should use 'journal' so Claude edits the right field."""
        entry = {"key": "X", "entry_type": "article", "journal": "arXiv preprint arXiv:2210.02747"}
        cr = {"journal": "Nature"}
        ms = compare_entry(entry, cr)
        venue_ms = [m for m in ms if m["field"] in ("journal", "booktitle")]
        assert len(venue_ms) == 1
        assert venue_ms[0]["field"] == "journal"


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
