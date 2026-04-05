#!/usr/bin/env python3
"""Tests for duplicates.py — duplicate detection in BibTeX files."""

import json
import os
import subprocess
import sys

import pytest

from duplicates import find_duplicates, normalize_title, remove_exact_duplicates
from parser import parse_bib_entries

TOOL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "skills", "bibtidy", "tools", "duplicates.py")


def _run(bib_text):
    """Parse *bib_text* and return the list of duplicate dicts."""
    return find_duplicates(parse_bib_entries(bib_text))


class TestSameKey:
    def test_exact_duplicate_key(self):
        bib = """
@article{Smith2020,
  author = {Smith, John},
  title  = {First paper},
  year   = {2020},
}

@inproceedings{Smith2020,
  author = {Smith, John},
  title  = {A completely different paper},
  year   = {2020},
}
"""
        same_key = [d for d in _run(bib) if d["type"] == "same_key"]
        assert len(same_key) == 1
        assert same_key[0]["key1"] == "Smith2020"
        assert same_key[0]["key2"] == "Smith2020"

    def test_three_same_keys(self):
        bib = """
@article{Foo, title={A}}
@article{Foo, title={B}}
@article{Foo, title={C}}
"""
        same_key = [d for d in _run(bib) if d["type"] == "same_key"]
        assert len(same_key) == 3  # 3 entries -> 3 pairs


class TestSameDOI:
    def test_same_doi_different_keys(self):
        bib = """
@article{Alpha, author={A}, title={Paper One}, doi={10.1234/foo}}
@article{Beta,  author={A}, title={Paper One Revised}, doi={10.1234/foo}}
"""
        same_doi = [d for d in _run(bib) if d["type"] == "same_doi"]
        assert len(same_doi) == 1
        assert "10.1234/foo" in same_doi[0]["detail"]

    def test_doi_case_insensitive(self):
        bib = """
@article{A1, doi = {10.1234/ABC}}
@article{A2, doi = {10.1234/abc}}
"""
        same_doi = [d for d in _run(bib) if d["type"] == "same_doi"]
        assert len(same_doi) == 1

    def test_legacy_dx_doi_url_matches_bare_doi(self):
        bib = """
@article{A1, doi = {https://dx.doi.org/10.1234/ABC}}
@article{A2, doi = {10.1234/abc}}
"""
        same_doi = [d for d in _run(bib) if d["type"] == "same_doi"]
        assert len(same_doi) == 1


class TestSameTitle:
    def test_normalized_match(self):
        bib = """
@article{X1, title={Deep Learning for NLP}, author={Smith, John}, journal={NeurIPS}}
@inproceedings{X2, title={deep learning for nlp}, author={Smith, John}, booktitle={NeurIPS}}
"""
        assert len([d for d in _run(bib) if d["type"] == "same_title"]) == 1

    def test_braces_stripped(self):
        bib = """
@article{A, title={{Deep} {Learning} for {NLP}}, author={Doe, Jane}, journal={ICML}}
@article{B, title={Deep Learning for NLP}, author={Doe, Jane}, journal={ICML}}
"""
        assert len([d for d in _run(bib) if d["type"] == "same_title"]) == 1

    def test_punctuation_stripped(self):
        bib = """
@article{P1, title={Hello, World: A Study!}, author={Turing, Alan}, journal={J1}}
@article{P2, title={Hello World A Study}, author={Turing, Alan}, journal={J1}}
"""
        assert len([d for d in _run(bib) if d["type"] == "same_title"]) == 1

    def test_no_shared_author_no_duplicate(self):
        """Same title but completely different authors should NOT be flagged."""
        bib = """
@article{S1, title={A Survey of Deep Learning}, author={Smith, Alice}, journal={J1}}
@article{S2, title={A Survey of Deep Learning}, author={Jones, Bob}, journal={J2}}
"""
        assert len([d for d in _run(bib) if d["type"] == "same_title"]) == 0

    def test_multiline_author_list_still_shares_author(self):
        bib = """
@article{S1, title={A Survey of Deep Learning}, author={Alpha, Alice and
 Beta, Bob}, journal={J1}}
@article{S2, title={A Survey of Deep Learning}, author={Beta, Bob}, journal={J2}}
"""
        assert len([d for d in _run(bib) if d["type"] == "same_title"]) == 1


class TestBraceOnlySyntax:
    def test_parenthesized_entry_rejected(self):
        bib = "@article(Smith2020, title={Hello}, year={2020})"
        with pytest.raises(ValueError, match="not supported"):
            parse_bib_entries(bib)

    def test_parenthesized_special_block_rejected(self):
        bib = """
@comment(ignored text)
@article{Real, title={Actual Paper}, journal={Nature}}
"""
        with pytest.raises(ValueError, match="not supported"):
            parse_bib_entries(bib)

    def test_parenthesized_entry_inside_brace_comment_ignored(self):
        bib = """
@comment{This block should be ignored verbatim
  @article(Ghost, title={Ignored})
}
@article{Real, title={Actual Paper}, journal={Nature}}
"""
        entries = parse_bib_entries(bib)
        assert [entry["key"] for entry in entries] == ["Real"]


class TestNoDuplicates:
    def test_empty_file(self):
        assert _run("") == []

    def test_single_entry(self):
        assert _run("@article{Solo, title={Only one}, year={2023}}") == []

    def test_distinct_entries(self):
        bib = """
@article{A, title={Alpha}, doi={10.1/a}, journal={J1}}
@article{B, title={Beta},  doi={10.1/b}, journal={J2}}
@article{C, title={Gamma}, doi={10.1/c}, journal={J3}}
        """
        assert _run(bib) == []

    def test_same_authors_preprint_and_published_without_shared_title_not_duplicate(self):
        bib = """
@article{Alpha2022, title={Diffusion models for protein design}, author={Smith, John and Doe, Jane and others}, journal={bioRxiv}, year={2022}}
@article{Alpha2023, title={Language models for code generation}, author={Smith, John and Doe, Jane and others}, journal={Nature}, year={2023}}
"""
        assert _run(bib) == []


class TestLatexNormalization:
    def test_textbf_stripped(self):
        assert normalize_title(r"\textbf{Bold} Title") == normalize_title("Bold Title")

    def test_emph_stripped(self):
        assert normalize_title(r"\emph{Italic} Text") == normalize_title("Italic Text")

    def test_multiple_commands(self):
        assert normalize_title(r"\textbf{\emph{Nested}} and \textit{more}") == normalize_title("Nested and more")

    def test_accent_commands(self):
        norm = normalize_title(r"Caf\'{e} au lait")
        assert "caf" in norm
        assert "lait" in norm

    def test_heavy_latex(self):
        bib = r"""
@article{L1, title={\textbf{A} {Novel} \emph{Approach} to \textsc{Machine} Learning}, author={Doe, Jane}, journal={ICML}}
@article{L2, title={A Novel Approach to Machine Learning}, author={Doe, Jane}, journal={ICML}}
"""
        assert len([d for d in _run(bib) if d["type"] == "same_title"]) == 1

    def test_utf8_matches_latex_accent(self):
        """UTF-8 'é' and LaTeX \\'{e} should normalize to the same string."""
        assert normalize_title("Café") == normalize_title(r"Caf\'{e}")

    def test_utf8_duplicate_detection(self):
        bib = """
@article{A, title={Café au lait}, author={Dupont, Jean}, journal={J1}}
@article{B, title={Caf\\'{e} au lait}, author={Dupont, Jean}, journal={J1}}
"""
        assert len([d for d in _run(bib) if d["type"] == "same_title"]) == 1


class TestSkipSpecialBlocks:
    def test_string_preamble_comment_skipped(self):
        bib = """
@string{jml = {Journal of Machine Learning}}
@preamble{"This is a preamble"}
@comment{This entire block should be ignored
  @article{Ghost, title={Should not appear}}
}
@article{Real1, title={Actual Paper}, journal={Nature}}
"""
        entries = parse_bib_entries(bib)
        keys = [e["key"] for e in entries]
        assert "jml" not in keys
        assert "Ghost" not in keys
        assert len(entries) == 1
        assert entries[0]["key"] == "Real1"

    def test_no_false_positives_with_special_blocks(self):
        bib = """
@string{ieee = {IEEE}}
@preamble{"preamble text"}
@article{Only, title={Unique}, journal={Nature}}
"""
        assert _run(bib) == []


class TestCLI:
    def test_cli_output_json(self, tmp_path):
        bib_file = tmp_path / "test.bib"
        bib_file.write_text("""
@article{Dup, title={Same}, year={2020}}
@article{Dup, title={Other}, year={2021}}
""")
        result = subprocess.run([sys.executable, TOOL_PATH, str(bib_file)], capture_output=True, text=True)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["type"] == "same_key"

    def test_cli_no_args(self):
        result = subprocess.run([sys.executable, TOOL_PATH], capture_output=True, text=True)
        assert result.returncode != 0

    def test_cli_parenthesized_entry_rejected(self, tmp_path):
        bib_file = tmp_path / "paren.bib"
        bib_file.write_text("@article(ParenKey, title={Same}, year={2020})\n")
        result = subprocess.run([sys.executable, TOOL_PATH, str(bib_file)], capture_output=True, text=True)
        assert result.returncode == 1
        assert "not supported" in result.stderr


class TestQuotedValues:
    def test_quoted_doi(self):
        bib = """
@article{Q1, doi = "10.9999/test"}
@article{Q2, doi = "10.9999/test"}
"""
        assert len([d for d in _run(bib) if d["type"] == "same_doi"]) == 1

    def test_concatenated_value(self):
        bib = """
@article{C1, title = {Deep} # { Learning}, author={Doe, Jane}, journal={J}}
@article{C2, title = {Deep Learning}, author={Doe, Jane}, journal={J}}
        """
        assert len([d for d in _run(bib) if d["type"] == "same_title"]) == 1

    def test_preprint_published_pair_with_changed_title_detected(self):
        bib = """
@article{watson2022broadly,
  title={Broadly applicable and accurate protein design by integrating structure prediction networks and diffusion generative models},
  author={Watson, Joseph L and Juergens, David and Bennett, Nathaniel R and Trippe, Brian L and Yim, Jason and Eisenach, Helen E and Ahern, Woody and Borst, Andrew J and Ragotte, Robert J and Milles, Lukas F and others},
  journal={BioRxiv},
  pages={2022--12},
  year={2022}
}

@article{watson2023novo,
  title={De novo design of protein structure and function with RFdiffusion},
  author={Watson, Joseph L and Juergens, David and Bennett, Nathaniel R and Trippe, Brian L and Yim, Jason and Eisenach, Helen E and Ahern, Woody and Borst, Andrew J and Ragotte, Robert J and Milles, Lukas F and others},
  journal={Nature},
  volume={620},
  pages={1089--1100},
  year={2023}
}
"""
        dups = _run(bib)
        assert [d for d in dups if d["type"] == "preprint_published"]


class TestCommentedOutEntries:
    def test_bibtidy_comments_skipped(self):
        """Commented-out originals from bibtidy output should not be parsed."""
        bib = """
% @article{hyvarinen2005estimation,
%   title={Estimation of non-normalized statistical models by score matching.},
%   author={Hyv{\\"a}rinen, Aapo and Dayan, Peter},
%   journal={Journal of Machine Learning Research},
%   volume={6},
%   number={4},
%   year={2005}
% }
% bibtidy: https://jmlr.org/papers/v6/hyvarinen05a.html
@article{hyvarinen2005estimation,
  title={Estimation of non-normalized statistical models by score matching},
  author={Hyv{\\"a}rinen, Aapo},
  journal={Journal of Machine Learning Research},
  volume={6},
  number={24},
  year={2005}
}
"""
        entries = parse_bib_entries(bib)
        assert len(entries) == 1
        assert entries[0]["key"] == "hyvarinen2005estimation"

    def test_no_false_duplicates_on_rerun(self):
        """Running duplicates on bibtidy output should not report false duplicates."""
        bib = """
% @article{foo2020,
%   title={Some Paper},
%   author={Foo, Bar},
%   year={2020}
% }
@article{foo2020,
  title={Some Paper},
  author={Foo, Bar},
  year={2020}
}
"""
        assert _run(bib) == []


class TestDOIURLNormalization:
    def test_url_prefix_vs_bare(self):
        """DOIs with and without https://doi.org/ prefix should be detected as duplicates."""
        bib = """
@article{A1, title={Paper A}, doi={https://doi.org/10.1234/foo}}
@article{A2, title={Paper B}, doi={10.1234/foo}}
"""
        same_doi = [d for d in _run(bib) if d["type"] == "same_doi"]
        assert len(same_doi) == 1

    def test_http_prefix(self):
        bib = """
@article{B1, title={Paper A}, doi={http://doi.org/10.1234/bar}}
@article{B2, title={Paper B}, doi={10.1234/bar}}
"""
        same_doi = [d for d in _run(bib) if d["type"] == "same_doi"]
        assert len(same_doi) == 1


class TestEscapedBraces:
    def test_escaped_braces_in_title(self):
        """Escaped braces \\{ and \\} should not affect depth counting."""
        bib = r"""
@article{A, title={Review of the \{ symbol\}}, author={Smith, John}, year={2020}}
"""
        entries = parse_bib_entries(bib)
        assert len(entries) == 1
        assert entries[0]["key"] == "A"
        assert r"\{ symbol\}" in entries[0]["title"]

    def test_escaped_braces_no_false_duplicate(self):
        """Entries with escaped braces should parse correctly and not produce false duplicates."""
        bib = r"""
@article{A, title={Set \{x : x > 0\}}, author={Doe, Jane}, journal={J1}}
@article{B, title={A different paper}, author={Smith, John}, journal={J2}}
"""
        assert _run(bib) == []


class TestExactDuplicates:
    def test_identical_entries(self):
        bib = "\n".join(
            [
                "@article{Smith2020,",
                "  title={Deep Learning},",
                "  author={Smith, John},",
                "  year={2020},",
                "}",
                "",
                "@article{Smith2020,",
                "  title={Deep Learning},",
                "  author={Smith, John},",
                "  year={2020},",
                "}",
            ]
        )
        _, count = remove_exact_duplicates(bib)
        assert count == 1

    def test_whitespace_differences_are_exact(self):
        """Extra whitespace should not prevent exact match."""
        bib = "\n".join(
            [
                "@article{A, title={Deep  Learning}, author={Smith, John}, year={2020}}",
                "@article{A, title={Deep Learning}, author={Smith, John}, year={2020}}",
            ]
        )
        _, count = remove_exact_duplicates(bib)
        assert count == 1

    def test_different_fields_not_exact(self):
        bib = "\n".join(
            [
                "@article{A, title={Paper One}, author={Smith, John}, year={2020}}",
                "@article{A, title={Paper One}, author={Smith, John}, year={2021}}",
            ]
        )
        _, count = remove_exact_duplicates(bib)
        assert count == 0

    def test_different_type_not_exact(self):
        bib = "\n".join(
            [
                "@article{A, title={Paper}, author={Smith, John}, year={2020}}",
                "@inproceedings{A, title={Paper}, author={Smith, John}, year={2020}}",
            ]
        )
        _, count = remove_exact_duplicates(bib)
        assert count == 0

    def test_different_key_not_exact(self):
        bib = "\n".join(
            [
                "@article{A, title={Paper}, author={Smith, John}, year={2020}}",
                "@article{B, title={Paper}, author={Smith, John}, year={2020}}",
            ]
        )
        _, count = remove_exact_duplicates(bib)
        assert count == 0

    def test_three_identical_keeps_first(self):
        bib = "\n".join(
            [
                "@article{X, title={Same}, year={2020}}",
                "@article{X, title={Same}, year={2020}}",
                "@article{X, title={Same}, year={2020}}",
            ]
        )
        _, count = remove_exact_duplicates(bib)
        assert count == 2

    def test_no_entries(self):
        _, count = remove_exact_duplicates("")
        assert count == 0


class TestRemoveExactDuplicates:
    def test_comments_out_duplicate(self):
        bib = "@article{A,\n  title={Paper},\n  year={2020}\n}\n\n@article{A,\n  title={Paper},\n  year={2020}\n}\n"
        result, count = remove_exact_duplicates(bib)
        assert count == 1
        assert "% bibtidy: exact duplicate, commented out" in result
        assert result.count("% @article{A,") == 1
        # First entry still present uncommented
        entries = parse_bib_entries(result)
        assert len(entries) == 1

    def test_no_duplicates_unchanged(self):
        bib = "@article{A, title={One}, year={2020}}\n@article{B, title={Two}, year={2021}}\n"
        result, count = remove_exact_duplicates(bib)
        assert count == 0
        assert result == bib

    def test_rejects_parenthesized_entry(self):
        bib = "@article(ParenKey, title={Same}, year={2020})\n"
        with pytest.raises(ValueError, match="not supported"):
            remove_exact_duplicates(bib)

    def test_cli_remove_exact(self, tmp_path):
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(
            "@article{A,\n  title={Paper},\n  year={2020}\n}\n\n@article{A,\n  title={Paper},\n  year={2020}\n}\n"
        )
        result = subprocess.run([sys.executable, TOOL_PATH, str(bib_file), "--exact"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "Removed 1" in result.stdout
        content = bib_file.read_text()
        assert "% bibtidy: exact duplicate" in content

    def test_cli_remove_exact_parenthesized_entry_rejected_without_rewrite(self, tmp_path):
        bib_file = tmp_path / "test.bib"
        original = (
            "@article{A,\n  title={Paper},\n  year={2020}\n}\n\n"
            "@article{A,\n  title={Paper},\n  year={2020}\n}\n\n"
            "@article(ParenKey, title={Same}, year={2020})\n"
        )
        bib_file.write_text(original)
        result = subprocess.run([sys.executable, TOOL_PATH, str(bib_file), "--exact"], capture_output=True, text=True)
        assert result.returncode == 1
        assert "not supported" in result.stderr
        assert bib_file.read_text() == original
