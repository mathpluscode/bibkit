#!/usr/bin/env python3
"""Tests for duplicates.py — duplicate detection in BibTeX files."""

import json
import os
import subprocess
import sys

from duplicates import find_duplicates, is_preprint, normalize_title, parse_bib_entries

TOOL_PATH = os.path.join(os.path.dirname(__file__), "..", "skills", "bibtidy", "tools", "duplicates.py")


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


class TestPreprintPublished:
    def test_arxiv_and_journal(self):
        bib = """
@article{ArxivVer, title={Attention Is All You Need}, journal={arXiv preprint arXiv:1706.03762}}
@article{PublishedVer, title={Attention Is All You Need}, journal={Advances in Neural Information Processing Systems}}
"""
        pp = [d for d in _run(bib) if d["type"] == "preprint_published"]
        assert len(pp) == 1
        assert pp[0]["key1"] == "ArxivVer"
        assert pp[0]["key2"] == "PublishedVer"

    def test_biorxiv(self):
        bib = """
@article{Pre, title={Protein Folding}, journal={bioRxiv}}
@article{Pub, title={Protein Folding}, journal={Nature}}
"""
        assert len([d for d in _run(bib) if d["type"] == "preprint_published"]) == 1

    def test_chemrxiv(self):
        bib = """
@article{Pre, title={Novel Catalyst}, journal={ChemRxiv}}
@article{Pub, title={Novel Catalyst}, journal={JACS}}
"""
        assert len([d for d in _run(bib) if d["type"] == "preprint_published"]) == 1


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


class TestExpandedPreprintDetection:
    def test_eprint_field(self):
        entry = {"key": "X", "eprint": "2301.12345", "archiveprefix": "arXiv"}
        assert is_preprint(entry) is True

    def test_eprint_numeric_only(self):
        entry = {"key": "X", "eprint": "2301.12345"}
        assert is_preprint(entry) is True

    def test_note_field(self):
        entry = {"key": "X", "note": "arXiv preprint arXiv:2301.12345"}
        assert is_preprint(entry) is True

    def test_howpublished_field(self):
        entry = {"key": "X", "howpublished": "bioRxiv"}
        assert is_preprint(entry) is True

    def test_archiveprefix_alone(self):
        entry = {"key": "X", "archiveprefix": "arXiv"}
        assert is_preprint(entry) is True

    def test_not_preprint(self):
        entry = {"key": "X", "journal": "Nature"}
        assert is_preprint(entry) is False


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
% bibtidy: source https://jmlr.org/papers/v6/hyvarinen05a.html
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
