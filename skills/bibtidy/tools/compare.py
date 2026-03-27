#!/usr/bin/env python3
"""Compare BibTeX entries against CrossRef metadata.

Returns a JSON list of field-level mismatches for each entry,
so the caller knows exactly what needs fixing.

Usage:
    python3 compare.py <file.bib>              — compare all entries
    python3 compare.py <file.bib> --key KEY    — compare a single entry

Options:
    --timeout SECONDS   HTTP timeout per request (default: 10)
"""

import argparse
import json
import re
import sys

from crossref import fetch_doi, search_title
from duplicates import parse_bib_entries


def _normalize_pages(pages: str) -> str:
    """Normalize page ranges: strip spaces, convert -- to -."""
    return re.sub(r"\s*-+\s*", "-", pages.strip())


def _normalize_doi(doi: str) -> str:
    """Strip URL prefix and lowercase."""
    doi = re.sub(r"^https?://doi\.org/", "", doi.strip())
    return doi.lower()


def _normalize_title(title: str) -> str:
    """Lowercase, strip braces, collapse whitespace for comparison."""
    t = title.lower()
    t = t.replace("{", "").replace("}", "")
    t = re.sub(r"\\[a-zA-Z]+\s*", "", t)
    t = re.sub(r"\\.", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalize_author_list(authors_str: str) -> list[str]:
    """Parse 'Last, First and Last, First' into sorted lowercase last names."""
    names = []
    for name in authors_str.split(" and "):
        name = name.strip()
        if not name or name == "others":
            continue
        if "," in name:
            last = name.split(",")[0].strip()
        else:
            parts = name.split()
            last = parts[-1] if parts else ""
        last = last.replace("{", "").replace("}", "")
        last = re.sub(r"\\.", "", last)
        names.append(last.lower())
    return sorted(names)


def _crossref_author_last_names(authors: list[str]) -> list[str]:
    """Extract sorted lowercase last names from CrossRef 'Last, First' strings."""
    names = []
    for a in authors:
        if "," in a:
            last = a.split(",")[0].strip().lower()
        else:
            parts = a.split()
            last = parts[-1].lower() if parts else ""
        names.append(last)
    return sorted(names)


def compare_entry(entry: dict, crossref: dict) -> list[dict]:
    """Compare a parsed BibTeX entry against CrossRef metadata.

    Returns a list of mismatch dicts with keys:
        field, bib_value, crossref_value, severity
    """
    mismatches = []

    def _add(field, bib_val, cr_val, severity="fix"):
        mismatches.append({
            "field": field,
            "bib_value": bib_val,
            "crossref_value": cr_val,
            "severity": severity,
        })

    # Title
    bib_title = entry.get("title", "")
    cr_title = crossref.get("title") or ""
    if bib_title and cr_title:
        if _normalize_title(bib_title) != _normalize_title(cr_title):
            _add("title", bib_title, cr_title)

    # Authors (compare last names only — first name formats vary)
    bib_author = entry.get("author", "")
    cr_authors = crossref.get("authors", [])
    if bib_author and cr_authors:
        bib_names = _normalize_author_list(bib_author)
        cr_names = _crossref_author_last_names(cr_authors)
        # Ignore "others" truncation: only compare if bib has fewer unique names
        # that don't appear in CrossRef
        bib_set = set(bib_names)
        cr_set = set(cr_names)
        extra_in_bib = bib_set - cr_set
        missing_from_bib = cr_set - bib_set
        if extra_in_bib or (missing_from_bib and len(bib_names) >= len(cr_names)):
            _add("author", bib_author,
                 " and ".join(cr_authors), "review")

    # Year
    bib_year = entry.get("year", "").strip()
    cr_year = crossref.get("year") or ""
    if bib_year and cr_year and bib_year != cr_year:
        _add("year", bib_year, cr_year)

    # Journal / booktitle — use the actual field name from the entry
    bib_venue_field = "journal" if "journal" in entry else "booktitle" if "booktitle" in entry else None
    bib_venue = entry.get(bib_venue_field, "") if bib_venue_field else ""
    cr_venue = crossref.get("journal") or ""
    if bib_venue and cr_venue:
        is_preprint = re.search(
            r"\b(arxiv|biorxiv|chemrxiv)\b", bib_venue, re.IGNORECASE
        )
        if is_preprint:
            # Preprint upgraded to published venue
            if not re.search(r"\b(arxiv|biorxiv|chemrxiv)\b", cr_venue, re.IGNORECASE):
                _add(bib_venue_field, bib_venue, cr_venue)
        else:
            # Non-preprint venue mismatch (flag for review, don't auto-fix)
            if _normalize_title(bib_venue) != _normalize_title(cr_venue):
                _add(bib_venue_field, bib_venue, cr_venue, "review")

    # Volume
    bib_vol = entry.get("volume", "").strip()
    cr_vol = crossref.get("volume") or ""
    if cr_vol and bib_vol != cr_vol:
        _add("volume", bib_vol or None, cr_vol)

    # Number
    bib_num = entry.get("number", "").strip()
    cr_num = crossref.get("number") or ""
    if cr_num and bib_num != cr_num:
        _add("number", bib_num or None, cr_num)

    # Pages
    bib_pages = entry.get("pages", "").strip()
    cr_pages = crossref.get("pages") or ""
    if bib_pages and cr_pages:
        if _normalize_pages(bib_pages) != _normalize_pages(cr_pages):
            _add("pages", bib_pages, cr_pages)
    elif not bib_pages and cr_pages:
        _add("pages", None, cr_pages)

    # DOI
    bib_doi = entry.get("doi", "").strip()
    cr_doi = crossref.get("doi") or ""
    if bib_doi and cr_doi:
        if _normalize_doi(bib_doi) != _normalize_doi(cr_doi):
            _add("doi", bib_doi, cr_doi)
    elif not bib_doi and cr_doi:
        _add("doi", None, cr_doi, "review")

    # Entry type
    cr_type = crossref.get("type") or ""
    bib_type = entry.get("entry_type", "")
    if cr_type and bib_type and cr_type != bib_type:
        _add("entry_type", bib_type, cr_type, "review")

    return mismatches


def lookup_and_compare(entry: dict, timeout: int = 10) -> dict:
    """Fetch CrossRef data for an entry and compare fields.

    Returns a dict with: key, crossref_url, mismatches, error (if any).
    """
    key = entry["key"]
    result = {"key": key, "mismatches": [], "crossref_url": None, "error": None}

    # Try DOI first, then title search
    doi = entry.get("doi", "").strip()
    if doi:
        doi = re.sub(r"^https?://doi\.org/", "", doi)
        cr = fetch_doi(doi, timeout=timeout)
    else:
        title = entry.get("title", "")
        if not title:
            result["error"] = "No DOI or title to search"
            return result
        cr = search_title(title, rows=3, timeout=timeout)

    if "error" in cr:
        result["error"] = cr["error"]
        return result

    # For search results, pick the best match
    if "results" in cr:
        items = cr["results"]
        if not items:
            result["error"] = "No CrossRef results found"
            return result
        # Pick the result whose title best matches
        bib_title_norm = _normalize_title(entry.get("title", ""))
        best = None
        for item in items:
            if _normalize_title(item.get("title") or "") == bib_title_norm:
                best = item
                break
        if best is None:
            result["error"] = "No exact title match in CrossRef results"
            return result
        cr = best

    result["crossref_url"] = cr.get("url")
    result["mismatches"] = compare_entry(entry, cr)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare BibTeX entries against CrossRef metadata"
    )
    parser.add_argument("bibfile", help="Path to .bib file")
    parser.add_argument("--key", help="Only compare this citation key")
    parser.add_argument(
        "--timeout", type=int, default=10,
        help="HTTP timeout in seconds (default: 10)",
    )
    args = parser.parse_args()

    try:
        with open(args.bibfile, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.bibfile}", file=sys.stderr)
        sys.exit(1)

    entries = parse_bib_entries(text)
    if args.key:
        entries = [e for e in entries if e["key"] == args.key]
        if not entries:
            print(f"Error: key not found: {args.key}", file=sys.stderr)
            sys.exit(1)

    results = []
    for entry in entries:
        result = lookup_and_compare(entry, timeout=args.timeout)
        results.append(result)

    json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
