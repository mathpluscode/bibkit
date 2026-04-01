#!/usr/bin/env python3
"""Tests for fmt.py — format validation of bibtidy output."""

import os
import subprocess
import sys

from fmt import check_changed_entry, parse_entries

TOOL_PATH = os.path.join(os.path.dirname(__file__), "..", "skills", "bibtidy", "tools", "fmt.py")


class TestParseEntries:
    def test_single_entry(self):
        text = "@article{Smith2020,\n  title={Hello},\n  year={2020}\n}"
        entries = parse_entries(text)
        assert "Smith2020" in entries
        assert "@article{Smith2020," in entries["Smith2020"]["entry"]

    def test_entry_with_context(self):
        text = (
            "% @article{Smith2020,\n"
            "%   title={Old},\n"
            "% }\n"
            "% bibtidy: source https://example.com\n"
            "% bibtidy: fixed title\n"
            "@article{Smith2020,\n"
            "  title={New},\n"
            "  year={2020}\n"
            "}"
        )
        entries = parse_entries(text)
        assert "Smith2020" in entries
        assert "% bibtidy: source" in entries["Smith2020"]["context"]

    def test_multiple_entries(self):
        text = "@article{A,\n  title={Alpha}\n}\n\n@article{B,\n  title={Beta}\n}"
        entries = parse_entries(text)
        assert len(entries) == 2
        assert "A" in entries
        assert "B" in entries

    def test_nested_braces(self):
        text = "@article{X,\n  title={A {Nested} Title},\n  year={2020}\n}"
        entries = parse_entries(text)
        assert "X" in entries

    def test_special_chars_in_key(self):
        """Keys with dots/slashes should not break regex."""
        text = "@article{doi:10.1234/foo,\n  title={Test}\n}"
        entries = parse_entries(text)
        assert "doi:10.1234/foo" in entries


class TestCheckChangedEntry:
    def test_valid_changed_entry(self):
        context = (
            "% @article{Smith2020,\n"
            "%   title={Old Title},\n"
            "% }\n"
            "% bibtidy: source https://doi.org/10.1234/test\n"
            "% bibtidy: fixed title spelling"
        )
        errors = check_changed_entry("Smith2020", context)
        assert errors == []

    def test_missing_commented_original(self):
        context = "% bibtidy: source https://doi.org/10.1234/test\n% bibtidy: fixed title"
        errors = check_changed_entry("Smith2020", context)
        assert any("commented-out original" in e.lower() for e in errors)

    def test_incomplete_commented_original(self):
        context = (
            "% @article{Smith2020,\n"
            "%   title={Old},\n"
            "% bibtidy: source https://doi.org/10.1234/test\n"
            "% bibtidy: fixed title"
        )
        errors = check_changed_entry("Smith2020", context)
        assert any("incomplete" in e.lower() for e in errors)

    def test_missing_source_url(self):
        context = "% @article{Smith2020,\n%   title={Old},\n% }\n% bibtidy: fixed title"
        errors = check_changed_entry("Smith2020", context)
        assert any("source" in e.lower() for e in errors)

    def test_missing_explanation(self):
        context = "% @article{Smith2020,\n%   title={Old},\n% }\n% bibtidy: source https://doi.org/10.1234/test"
        errors = check_changed_entry("Smith2020", context)
        assert any("explanation" in e.lower() for e in errors)

    def test_key_with_special_regex_chars(self):
        """Keys containing regex metacharacters should not break."""
        context = (
            "% @article{doi:10.1234/foo,\n"
            "%   title={Old},\n"
            "% }\n"
            "% bibtidy: source https://doi.org/10.1234/foo\n"
            "% bibtidy: fixed something"
        )
        errors = check_changed_entry("doi:10.1234/foo", context)
        assert errors == []


class TestCLI:
    def test_clean_file(self, tmp_path):
        """File with no bibtidy comments should pass."""
        bib = tmp_path / "test.bib"
        bib.write_text("@article{A,\n  title={Hello}\n}\n")
        result = subprocess.run([sys.executable, TOOL_PATH, str(bib)], capture_output=True, text=True)
        assert result.returncode == 0
        assert "Format OK" in result.stdout

    def test_valid_changed_entry(self, tmp_path):
        orig = tmp_path / "orig.bib"
        orig.write_text("@article{A,\n  title={Old}\n}\n")
        modified = tmp_path / "mod.bib"
        modified.write_text(
            "% @article{A,\n"
            "%   title={Old}\n"
            "% }\n"
            "% bibtidy: source https://example.com\n"
            "% bibtidy: fixed title\n"
            "@article{A,\n"
            "  title={New}\n"
            "}\n"
        )
        result = subprocess.run([sys.executable, TOOL_PATH, str(orig), str(modified)], capture_output=True, text=True)
        assert result.returncode == 0

    def test_violation_detected(self, tmp_path):
        orig = tmp_path / "orig.bib"
        orig.write_text("@article{A,\n  title={Old}\n}\n")
        modified = tmp_path / "mod.bib"
        modified.write_text("% bibtidy: fixed title\n@article{A,\n  title={New}\n}\n")
        result = subprocess.run([sys.executable, TOOL_PATH, str(orig), str(modified)], capture_output=True, text=True)
        assert result.returncode == 1
        assert "VIOLATION" in result.stdout

    def test_no_args(self):
        result = subprocess.run([sys.executable, TOOL_PATH], capture_output=True, text=True)
        assert result.returncode == 1
