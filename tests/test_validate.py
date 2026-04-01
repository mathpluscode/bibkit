#!/usr/bin/env python3
"""Tests for validate.py — structural validation helpers."""

import os

import pytest

from duplicates import parse_bib_entries

from validate import find_entry_block, find_commented_entry, get_field, has_bibtidy_comment, has_source_url


SAMPLE_ENTRY = "@article{Smith2020,\n  title={A {Nested} Title},\n  author={Smith, John},\n  year={2020}\n}"

SAMPLE_CHANGED = (
    "% @article{Smith2020,\n"
    "%   title={Old Title},\n"
    "% }\n"
    "% bibtidy: source https://doi.org/10.1234/test\n"
    "% bibtidy: fixed title\n"
    "@article{Smith2020,\n"
    "  title={New Title},\n"
    "  year={2020}\n"
    "}"
)


class TestFindEntryBlock:
    def test_finds_entry(self):
        result = find_entry_block(SAMPLE_ENTRY, "Smith2020")
        assert result is not None
        assert "Smith2020" in result
        assert "title={A {Nested} Title}" in result

    def test_handles_nested_braces(self):
        text = "@article{X,\n  title={A {B {C}} D},\n  year={2020}\n}"
        result = find_entry_block(text, "X")
        assert result is not None
        assert "A {B {C}} D" in result

    def test_returns_none_for_missing_key(self):
        assert find_entry_block(SAMPLE_ENTRY, "Missing") is None

    def test_ignores_commented_entry(self):
        text = "% @article{Ghost,\n%   title={Hidden}\n% }\n"
        assert find_entry_block(text, "Ghost") is None

    def test_key_with_special_chars(self):
        text = "@article{doi:10.1234/foo,\n  title={Test}\n}"
        result = find_entry_block(text, "doi:10.1234/foo")
        assert result is not None


class TestFindCommentedEntry:
    def test_found(self):
        assert find_commented_entry(SAMPLE_CHANGED, "Smith2020") is True

    def test_not_found(self):
        assert find_commented_entry(SAMPLE_ENTRY, "Smith2020") is False

    def test_key_with_special_chars(self):
        text = "% @article{doi:10.1234/foo,\n%   title={Old}\n% }\n"
        assert find_commented_entry(text, "doi:10.1234/foo") is True


class TestGetField:
    def test_simple_field(self):
        assert get_field(SAMPLE_ENTRY, "year") == "2020"

    def test_nested_braces(self):
        assert get_field(SAMPLE_ENTRY, "title") == "A {Nested} Title"

    def test_missing_field(self):
        assert get_field(SAMPLE_ENTRY, "doi") is None

    def test_case_insensitive(self):
        text = "@article{X,\n  Title={Hello}\n}"
        assert get_field(text, "title") == "Hello"


class TestHasBibtidyComment:
    def test_found(self):
        assert has_bibtidy_comment(SAMPLE_CHANGED, "Smith2020", r"% bibtidy: fixed") is True

    def test_not_found(self):
        assert has_bibtidy_comment(SAMPLE_ENTRY, "Smith2020", r"% bibtidy:") is False

    def test_source_url(self):
        assert has_source_url(SAMPLE_CHANGED, "Smith2020") is True

    def test_no_source_url(self):
        assert has_source_url(SAMPLE_ENTRY, "Smith2020") is False

    def test_duplicate_flag(self):
        text = "% bibtidy: DUPLICATE of Other — consider removing\n@article{Dup,\n  title={Test}\n}"
        assert has_bibtidy_comment(text, "Dup", r"DUPLICATE") is True


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Every field-level difference between input.bib and expected.bib must be
# declared here.  If someone updates expected.bib with a new correction,
# this test fails until the change is explicitly registered — preventing
# silent drift between the fixtures and validate.py checks.
#
# Format:  key -> { field: (input_value_or_None, expected_value_or_None) }
# Use None for fields that are absent in one file.
EXPECTED_DIFFS = {
    "hyvarinen2005estimation": {
        "title": (
            "Estimation of non-normalized statistical models by score matching.",
            "Estimation of non-normalized statistical models by score matching",
        ),
        "author": ('Hyv{\\"a}rinen, Aapo and Dayan, Peter', 'Hyv{\\"a}rinen, Aapo'),
        "number": ("4", "24"),
    },
    "lipman2022flow": {
        "entry_type": ("article", "inproceedings"),
        "journal": ("arXiv preprint arXiv:2210.02747", None),
        "booktitle": (None, "International Conference on Learning Representations"),
        "year": ("2022", "2023"),
    },
    "ho2020denoising": {
        "pages": ("6840-6851", "6840--6851"),
        "doi": ("https://doi.org/10.48550/arXiv.2006.11239", "10.48550/arXiv.2006.11239"),
    },
    "strudel2021segmenter": {"pages": ("7262--7272", "7242--7252")},
    "khader2022medical": {
        "title": (
            "Medical Diffusion--Denoising Diffusion Probabilistic Models for 3D Medical Image Generation",
            "Denoising Diffusion Probabilistic Models for 3D Medical Image Generation",
        ),
        "journal": ("arXiv preprint arXiv:2211.03364", "Scientific Reports"),
        "volume": (None, "13"),
        "year": ("2022", "2023"),
    },
}


class TestFixtureDiffs:
    """Ensure every field difference between input.bib and expected.bib is declared."""

    @pytest.fixture(scope="class")
    def entries(self):
        with open(os.path.join(FIXTURES_DIR, "input.bib")) as f:
            input_entries = {e["key"]: e for e in parse_bib_entries(f.read())}
        with open(os.path.join(FIXTURES_DIR, "expected.bib")) as f:
            expected_entries = {e["key"]: e for e in parse_bib_entries(f.read())}
        return input_entries, expected_entries

    def test_no_undeclared_diffs(self, entries):
        """Fail if expected.bib has field changes not listed in EXPECTED_DIFFS."""
        input_entries, expected_entries = entries
        undeclared = []
        for key in input_entries:
            inp = input_entries[key]
            exp = expected_entries.get(key)
            if exp is None:
                undeclared.append(f"  {key}: missing from expected.bib")
                continue
            all_fields = set(inp.keys()) | set(exp.keys())
            for field in all_fields:
                if field == "key":
                    continue
                iv = inp.get(field)
                ev = exp.get(field)
                if iv == ev:
                    continue
                declared = EXPECTED_DIFFS.get(key, {}).get(field)
                if declared is None:
                    undeclared.append(f"  {key}.{field}: {iv!r} → {ev!r} (not in EXPECTED_DIFFS)")
                elif declared != (iv, ev):
                    undeclared.append(f"  {key}.{field}: declared {declared} but actual {(iv, ev)}")
        assert not undeclared, "Undeclared field differences between input.bib and expected.bib:\n" + "\n".join(
            undeclared
        )

    def test_no_stale_diffs(self, entries):
        """Fail if EXPECTED_DIFFS declares a change that no longer exists."""
        input_entries, expected_entries = entries
        stale = []
        for key, fields in EXPECTED_DIFFS.items():
            inp = input_entries.get(key)
            exp = expected_entries.get(key)
            if inp is None or exp is None:
                stale.append(f"  {key}: entry missing from fixtures")
                continue
            for field, (old, new) in fields.items():
                iv = inp.get(field)
                ev = exp.get(field)
                if (iv, ev) != (old, new):
                    stale.append(f"  {key}.{field}: declared ({old!r}, {new!r}) but actual ({iv!r}, {ev!r})")
        assert not stale, "Stale entries in EXPECTED_DIFFS:\n" + "\n".join(stale)
