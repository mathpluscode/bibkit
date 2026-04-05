#!/usr/bin/env python3
"""Tests for validate.py — structural validation helpers."""

import os

import pytest

from parser import parse_bib_entries

from validate import find_entry_block, find_commented_entry, get_field, has_bibtidy_comment, has_url


SAMPLE_ENTRY = "@article{Smith2020,\n  title={A {Nested} Title},\n  author={Smith, John},\n  year={2020}\n}"

SAMPLE_CHANGED = (
    "% @article{Smith2020,\n"
    "%   title={Old Title},\n"
    "% }\n"
    "% bibtidy: https://doi.org/10.1234/test\n"
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

    def test_parenthesized_entry_rejected(self):
        with pytest.raises(ValueError, match="not supported"):
            find_entry_block("@article(Smith2020,\n  title={A (Nested) Title}\n)", "Smith2020")

    def test_parenthesized_text_inside_brace_comment_ignored(self):
        text = "@comment{ignored\n  @article(ghost, title={Ignored})\n}\n@article{Real,\n  title={Shown}\n}"
        result = find_entry_block(text, "Real")
        assert result is not None
        assert "title={Shown}" in result

    def test_ghost_entry_inside_comment_not_found(self):
        """Brace-style entry nested inside @comment{...} should not be found."""
        text = "@comment{ignored\n  @article{Ghost, title={Hidden}}\n}\n@article{Real,\n  title={Shown}\n}"
        assert find_entry_block(text, "Ghost") is None
        result = find_entry_block(text, "Real")
        assert result is not None


class TestFindCommentedEntry:
    def test_found(self):
        assert find_commented_entry(SAMPLE_CHANGED, "Smith2020") is True

    def test_not_found(self):
        assert find_commented_entry(SAMPLE_ENTRY, "Smith2020") is False

    def test_key_with_special_chars(self):
        text = "% @article{doi:10.1234/foo,\n%   title={Old}\n% }\n"
        assert find_commented_entry(text, "doi:10.1234/foo") is True

    def test_indented_commented_entry(self):
        """Indented commented originals like '%   @article{A,' should be found."""
        text = "%   @article{Smith2020,\n%     title={Old},\n%   }\n@article{Smith2020,\n  title={New}\n}"
        assert find_commented_entry(text, "Smith2020") is True

    def test_parenthesized_entry_rejected(self):
        with pytest.raises(ValueError, match="not supported"):
            find_commented_entry("@article(Smith2020,\n  title={A}\n)", "Smith2020")


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

    def test_has_url(self):
        assert has_url(SAMPLE_CHANGED, "Smith2020") is True

    def test_no_url(self):
        assert has_url(SAMPLE_ENTRY, "Smith2020") is False

    def test_duplicate_flag(self):
        text = "% bibtidy: DUPLICATE of Other — consider removing\n@article{Dup,\n  title={Test}\n}"
        assert has_bibtidy_comment(text, "Dup", r"DUPLICATE") is True

    def test_parenthesized_entry_rejected(self):
        with pytest.raises(ValueError, match="not supported"):
            has_bibtidy_comment("@article(Smith2020,\n  title={A}\n)", "Smith2020", r"% bibtidy:")


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
    "watson2023novo": {
        "author": (
            "Watson, Joseph L and Juergens, David and Bennett, Nathaniel R and Trippe, Brian L"
            " and Yim, Jason and Eisenach, Helen E and Ahern, Woody and Borst, Andrew J"
            " and Ragotte, Robert J and Milles, Lukas F and others",
            "Watson, Joseph L. and Juergens, David and Bennett, Nathaniel R. and Trippe, Brian L."
            " and Yim, Jason and Eisenach, Helen E. and Ahern, Woody and Borst, Andrew J."
            " and Ragotte, Robert J. and Milles, Lukas F. and Wicky, Basile I. M. and Hanikel, Nikita"
            " and Pellock, Samuel J. and Courbet, Alexis and Sheffler, William and Wang, Jue"
            " and Venkatesh, Preetham and Sappington, Isaac and Torres, Susana V\u00e1zquez"
            " and Lauko, Anna and De Bortoli, Valentin and Mathieu, Emile and Ovchinnikov, Sergey"
            " and Barzilay, Regina and Jaakkola, Tommi S. and DiMaio, Frank and Baek, Minkyung"
            " and Baker, David",
        ),
        "number": (None, "7976"),
    },
    "kirillov2023segment": {
        "author": (
            "Kirillov, Alexander and Mintun, Eric and Ravi, Nikhila and Mao, Hanzi"
            " and Rolland, Chloe and Gustafson, Laura and Xiao, Tete and Whitehead, Spencer"
            " and Berg, Alexander C and Lo, Wan-Yen and others",
            "Kirillov, Alexander and Mintun, Eric and Ravi, Nikhila and Mao, Hanzi"
            " and Rolland, Chloe and Gustafson, Laura and Xiao, Tete and Whitehead, Spencer"
            " and Berg, Alexander C and Lo, Wan-Yen and Doll{\\'a}r, Piotr and Girshick, Ross",
        )
    },
    "tzou2022coronavirus": {},
    "aichberger2025semantically": {
        "title": (
            "Semantically Diverse Language Generation",
            "Improving Uncertainty Estimation through Semantically Diverse Language Generation",
        ),
        "author": (
            "Aichberger, Franz and Chen, Lily and Smith, John",
            "Aichberger, Lukas and Schweighofer, Kajetan and Ielanskyi, Mykyta and Hochreiter, Sepp",
        ),
    },
}

# Entries that are commented out in expected.bib (e.g. hallucinated references).
EXPECTED_COMMENTED_OUT = {"wang2021identity"}


class TestFixtureDiffs:
    """Ensure every field difference between input.bib and expected.bib is declared."""

    @pytest.fixture(scope="class")
    def entries(self):
        with open(os.path.join(FIXTURES_DIR, "input.bib")) as f:
            input_entries = {e["key"]: e for e in parse_bib_entries(f.read())}
        with open(os.path.join(FIXTURES_DIR, "expected.bib")) as f:
            expected_entries = {e["key"]: e for e in parse_bib_entries(f.read())}
        return input_entries, expected_entries

    def test_commented_out_entries_present(self, entries):
        """Fail if EXPECTED_COMMENTED_OUT names an entry not commented in expected.bib."""
        with open(os.path.join(FIXTURES_DIR, "expected.bib")) as f:
            expected_text = f.read()
        missing = []
        for key in EXPECTED_COMMENTED_OUT:
            if not find_commented_entry(expected_text, key):
                missing.append(f"  {key}: not found as a commented-out entry in expected.bib")
        assert not missing, "EXPECTED_COMMENTED_OUT entries missing from expected.bib:\n" + "\n".join(missing)

    def test_no_undeclared_diffs(self, entries):
        """Fail if expected.bib has field changes not listed in EXPECTED_DIFFS."""
        input_entries, expected_entries = entries
        undeclared = []
        for key in input_entries:
            if key in EXPECTED_COMMENTED_OUT:
                continue
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
