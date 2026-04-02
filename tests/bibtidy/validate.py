#!/usr/bin/env python3
"""Validate bibtidy output against expected structural properties.

Usage:
    # After running one of the end-to-end test scripts
    python3 tests/validate.py tests/bibtidy/fixtures/got_cc.bib
"""

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "skills" / "bibtidy" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from duplicates import ensure_brace_only_entries, is_escaped, remove_special_blocks  # noqa: E402


def read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def find_entry_block(text, key):
    """Find the active (non-commented) entry for a given key.
    Returns the entry from @type{key, to its closing brace."""
    ensure_brace_only_entries(text)
    cleaned = remove_special_blocks(text)
    # Find the non-commented entry start (search cleaned text to skip ghost entries)
    escaped_key = re.escape(key)
    start_match = re.search(rf"^[ \t]*@\w+\{{{escaped_key},", cleaned, re.MULTILINE)
    if not start_match:
        return None
    start = start_match.start()
    depth = 1
    i = start_match.end()
    while i < len(text) and depth > 0:
        if text[i] == "{" and not is_escaped(text, i):
            depth += 1
        elif text[i] == "}" and not is_escaped(text, i):
            depth -= 1
        i += 1
    return text[start:i] if depth == 0 else None


def find_commented_entry(text, key):
    """Check if there is a commented-out version of this entry."""
    ensure_brace_only_entries(text)
    cleaned = remove_special_blocks(text)
    escaped_key = re.escape(key)
    pattern = rf"^[ \t]*%\s*@\w+\{{{escaped_key},"
    return bool(re.search(pattern, cleaned, re.MULTILINE))


def get_field(entry, field):
    """Extract a field value from a bib entry, handling nested braces."""
    # Find the field start
    match = re.search(rf"{field}\s*=\s*\{{", entry, re.IGNORECASE)
    if not match:
        return None
    # Walk forward counting braces to find the matching close
    start = match.end()
    depth = 1
    i = start
    while i < len(entry) and depth > 0:
        if entry[i] == "{":
            depth += 1
        elif entry[i] == "}":
            depth -= 1
        i += 1
    return entry[start : i - 1] if depth == 0 else None


def has_bibtidy_comment(text, key, pattern):
    """Check if a bibtidy comment matching pattern appears near the entry.

    Scans backwards from the entry to the previous non-comment, non-blank line
    (or start of file), collecting the context region.
    """
    ensure_brace_only_entries(text)
    cleaned = remove_special_blocks(text)
    escaped_key = re.escape(key)
    entry_match = re.search(rf"^[ \t]*@\w+\{{{escaped_key},", cleaned, re.MULTILINE)
    if not entry_match:
        return False
    # Walk backwards line by line to find the context boundary
    before = text[: entry_match.start()]
    lines = before.split("\n")
    # Remove trailing empty string from split
    if lines and lines[-1] == "":
        lines.pop()
    context_start = len(lines)
    while context_start > 0:
        line = lines[context_start - 1]
        if line.startswith("%") or line.strip() == "":
            context_start -= 1
        else:
            break
    context_lines = lines[context_start:]
    region = "\n".join(context_lines)
    return bool(re.search(pattern, region, re.IGNORECASE))


def has_url(text, key):
    """Check that a bibtidy URL comment exists near the entry."""
    return has_bibtidy_comment(text, key, r"% bibtidy: https?://")


class TestResult:
    def __init__(self, name):
        self.name = name
        self.checks = []

    def check(self, condition, description):
        status = "PASS" if condition else "FAIL"
        self.checks.append((status, description))
        return condition

    def print_results(self):
        all_passed = all(s == "PASS" for s, _ in self.checks)
        icon = "OK" if all_passed else "FAIL"
        print(f"\n[{icon}] {self.name}")
        for status, desc in self.checks:
            marker = "  +" if status == "PASS" else "  -"
            print(f"  {marker} {desc}")
        return all_passed


def check_correct_entry_unchanged(text):
    """Correct entry should be left unchanged — no comments, no modifications."""
    t = TestResult("Correct entry unchanged (vaswani2017attention)")
    entry = find_entry_block(text, "vaswani2017attention")
    t.check(entry is not None, "Entry still exists")
    t.check(
        not find_commented_entry(text, "vaswani2017attention"), "No commented-out original (entry was not modified)"
    )
    t.check(not has_bibtidy_comment(text, "vaswani2017attention", r"% bibtidy:"), "No bibtidy comments added")
    if entry:
        t.check("Vaswani" in entry, "Author preserved")
        t.check("2017" in entry, "Year preserved")
    return t


def check_wrong_author_fixed(text):
    """Wrong co-author should be removed with commented original + source."""
    t = TestResult("Wrong co-author fixed (hyvarinen2005estimation)")
    entry = find_entry_block(text, "hyvarinen2005estimation")
    t.check(entry is not None, "Entry still exists")
    t.check(find_commented_entry(text, "hyvarinen2005estimation"), "Original entry commented out")
    t.check(has_url(text, "hyvarinen2005estimation"), "URL provided")
    if entry:
        t.check("Dayan" not in get_field(entry, "author"), "Dayan removed from authors")
        t.check("rinen" in (get_field(entry, "author") or ""), "Hyvärinen still listed as author")
        number = get_field(entry, "number")
        if number:
            t.check("24" in number, "Number corrected to 24")
    return t


def check_arxiv_upgraded_to_published(text):
    """arXiv preprint should be upgraded to published venue."""
    t = TestResult("arXiv upgraded to published venue (lipman2022flow)")
    entry = find_entry_block(text, "lipman2022flow")
    t.check(entry is not None, "Entry still exists")
    t.check(find_commented_entry(text, "lipman2022flow"), "Original entry commented out")
    t.check(has_url(text, "lipman2022flow"), "URL provided")
    if entry:
        t.check(
            "arxiv" not in entry.lower() or "arxiv" not in get_field(entry, "journal").lower()
            if get_field(entry, "journal")
            else True,
            "No longer listed as arXiv",
        )
        t.check("@inproceedings" in entry.lower() or "@article" in entry.lower(), "Entry type is valid")
    return t


def check_formatting_fixes_applied(text):
    """DOI prefix should be stripped, page hyphens fixed."""
    t = TestResult("Formatting fixes applied (ho2020denoising)")
    entry = find_entry_block(text, "ho2020denoising")
    t.check(entry is not None, "Entry still exists")
    t.check(find_commented_entry(text, "ho2020denoising"), "Original entry commented out")
    t.check(has_url(text, "ho2020denoising"), "URL provided")
    if entry:
        doi = get_field(entry, "doi")
        if doi:
            t.check("https://doi.org/" not in doi, "DOI URL prefix stripped")
        pages = get_field(entry, "pages")
        if pages:
            t.check("--" in pages, "Page range uses double hyphen")
    return t


def check_duplicates_flagged(text):
    """bioRxiv + published pair should be flagged as duplicates."""
    t = TestResult("Duplicate pair flagged (watson2022broadly / watson2023novo)")
    t.check(
        has_bibtidy_comment(text, "watson2022broadly", r"% bibtidy:.*[Dd][Uu][Pp][Ll][Ii][Cc][Aa][Tt][Ee]")
        or has_bibtidy_comment(text, "watson2023novo", r"% bibtidy:.*[Dd][Uu][Pp][Ll][Ii][Cc][Aa][Tt][Ee]"),
        "At least one entry flagged as duplicate",
    )
    # Both entries should still exist (bibtidy flags, doesn't delete)
    t.check(find_entry_block(text, "watson2022broadly") is not None, "watson2022broadly still exists")
    t.check(find_entry_block(text, "watson2023novo") is not None, "watson2023novo still exists")
    return t


def check_wrong_pages_fixed(text):
    """Wrong page numbers should be corrected via CrossRef."""
    t = TestResult("Wrong page numbers fixed (strudel2021segmenter)")
    entry = find_entry_block(text, "strudel2021segmenter")
    t.check(entry is not None, "Entry still exists")
    t.check(find_commented_entry(text, "strudel2021segmenter"), "Original entry commented out")
    t.check(has_url(text, "strudel2021segmenter"), "URL provided")
    if entry:
        pages = get_field(entry, "pages")
        if pages:
            t.check("7242" in pages, "Page range corrected to 7242")
            t.check("7262" not in pages, "Old incorrect page number removed")
    return t


def check_title_change_upgraded(text):
    """arXiv preprint with title change should be upgraded with new title."""
    t = TestResult("Published title change applied (khader2022medical)")
    entry = find_entry_block(text, "khader2022medical")
    t.check(entry is not None, "Entry still exists")
    t.check(find_commented_entry(text, "khader2022medical"), "Original entry commented out")
    t.check(has_url(text, "khader2022medical"), "URL provided")
    if entry:
        title = get_field(entry, "title") or ""
        t.check("Medical Diffusion" not in title, "arXiv-only title prefix removed")
        t.check("Denoising" in title, "Published title present")
        journal = get_field(entry, "journal") or ""
        t.check("arxiv" not in journal.lower(), "No longer listed as arXiv")
        t.check("Scientific Reports" in journal, "Journal updated to Scientific Reports")
    return t


def has_comment_near_commented_entry(text, key, pattern):
    """Check if a comment matching pattern appears near a commented-out entry.

    Scans backwards from the commented entry line, collecting comment/blank
    lines until a non-comment, non-blank line (or start of file) is reached.
    """
    escaped_key = re.escape(key)
    entry_match = re.search(rf"^[ \t]*%\s*@\w+\{{{escaped_key},", text, re.MULTILINE)
    if not entry_match:
        return False
    before = text[: entry_match.start()]
    lines = before.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    context_start = len(lines)
    while context_start > 0:
        line = lines[context_start - 1]
        if line.startswith("%") or line.strip() == "":
            context_start -= 1
        else:
            break
    context_lines = lines[context_start:]
    region = "\n".join(context_lines)
    return bool(re.search(pattern, region, re.IGNORECASE))


def check_hallucinated_entry_flagged(text):
    """Hallucinated entry should be commented out and flagged as NOT FOUND."""
    t = TestResult("Hallucinated entries flagged as NOT FOUND")
    keys = ["wang2021identity"]
    for key in keys:
        t.check(find_entry_block(text, key) is None, f"{key} is no longer active")
        t.check(find_commented_entry(text, key), f"{key} is commented out")
        t.check(has_comment_near_commented_entry(text, key, r"NOT FOUND"), f"NOT FOUND comment near {key}")
    return t


def check_hallucinated_metadata_fixed(text):
    """Entry with real paper but wrong title/authors should be corrected."""
    t = TestResult("Hallucinated metadata fixed (aichberger2025semantically)")
    entry = find_entry_block(text, "aichberger2025semantically")
    t.check(entry is not None, "Entry still exists")
    t.check(find_commented_entry(text, "aichberger2025semantically"), "Original entry commented out")
    t.check(has_url(text, "aichberger2025semantically"), "URL provided")
    if entry:
        title = get_field(entry, "title") or ""
        t.check("Improving Uncertainty" in title, "Title corrected to published version")
        author = get_field(entry, "author") or ""
        t.check("Hochreiter" in author, "Authors corrected")
        t.check("Smith" not in author, "Hallucinated authors removed")
    return t


def check_published_article_not_downgraded(text):
    """Published article should not be downgraded to a preprint."""
    t = TestResult("Published article not downgraded (tzou2022coronavirus)")
    entry = find_entry_block(text, "tzou2022coronavirus")
    t.check(entry is not None, "Entry still exists")
    if entry:
        journal = get_field(entry, "journal") or ""
        year = get_field(entry, "year") or ""
        doi = get_field(entry, "doi")
        t.check("plos" in journal.lower(), "Published journal preserved (not downgraded)")
        t.check("arxiv" not in journal.lower(), "Not downgraded to preprint")
        t.check(year == "2022", "Published year preserved")
        t.check(doi is None, "Missing DOI is not auto-added")
    return t


def test_entry_count(text):
    """Entry count should be preserved (bibtidy never deletes entries)."""
    t = TestResult("Entry count preserved")
    cleaned = remove_special_blocks(text)
    cleaned = re.sub(r"(?m)^[ \t]*%.*$", "", cleaned)
    all_at = re.findall(r"^[ \t]*@(\w+)\{", cleaned, re.MULTILINE)
    t.check(len(all_at) == 10, f"Expected 10 active entries, found {len(all_at)}")
    return t


def test_special_blocks(text):
    """@string and @preamble blocks should be preserved verbatim."""
    t = TestResult("Special blocks preserved (@string, @preamble)")
    t.check("@string{neurips" in text or "@string{neurips" in text.lower(), "@string{neurips} block present")
    t.check("@preamble{" in text.lower(), "@preamble block present")
    return t


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <output.bib>")
        sys.exit(1)

    text = read_file(sys.argv[1])
    try:
        ensure_brace_only_entries(text)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    tests = [
        test_entry_count(text),
        test_special_blocks(text),
        check_correct_entry_unchanged(text),
        check_wrong_author_fixed(text),
        check_arxiv_upgraded_to_published(text),
        check_formatting_fixes_applied(text),
        check_duplicates_flagged(text),
        check_wrong_pages_fixed(text),
        check_title_change_upgraded(text),
        check_hallucinated_metadata_fixed(text),
        check_published_article_not_downgraded(text),
        check_hallucinated_entry_flagged(text),
    ]

    print("=" * 50)
    print("bibtidy validation results")
    print("=" * 50)

    passed = 0
    failed = 0
    for t in tests:
        if t.print_results():
            passed += 1
        else:
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Total: {passed + failed} checks, {passed} passed, {failed} failed")
    print("=" * 50)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
