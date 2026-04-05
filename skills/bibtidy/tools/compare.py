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

from crossref import fetch_doi, search_bibliographic, search_title
from duplicates import normalize_doi, normalize_title, split_bibtex_authors
from parser import parse_bib_entries


def _normalize_pages(pages: str) -> str:
    """Normalize page ranges: strip spaces, convert -- to -."""
    return re.sub(r"\s*-+\s*", "-", pages.strip())


def _normalize_author_list(authors_str: str) -> list[str]:
    """Parse 'Last, First and Last, First' into ordered lowercase last names.

    Preserves order so first-author swaps are detected.
    """
    names = []
    for name in split_bibtex_authors(authors_str):
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
    return names


def _crossref_author_last_names(authors: list[str]) -> list[str]:
    """Extract ordered lowercase last names from CrossRef 'Last, First' strings."""
    names = []
    for a in authors:
        if "," in a:
            last = a.split(",")[0].strip().lower()
        else:
            parts = a.split()
            last = parts[-1].lower() if parts else ""
        names.append(last)
    return names


def _venue_field_for_entry(entry: dict) -> str:
    """Choose the BibTeX venue field that should be updated."""
    if "journal" in entry:
        return "journal"
    if "booktitle" in entry:
        return "booktitle"
    if entry.get("entry_type") == "inproceedings":
        return "booktitle"
    return "journal"


def compare_entry(entry: dict, crossref: dict) -> list[dict]:
    """Compare a parsed BibTeX entry against CrossRef metadata.

    Returns a list of mismatch dicts with keys:
        field, bib_value, crossref_value
    """
    mismatches = []

    def _add(field, bib_val, cr_val):
        mismatches.append({"field": field, "bib_value": bib_val, "crossref_value": cr_val})

    # Title
    bib_title = entry.get("title", "")
    cr_title = crossref.get("title") or ""
    if bib_title and cr_title:
        if normalize_title(bib_title) != normalize_title(cr_title):
            _add("title", bib_title, cr_title)
    elif not bib_title and cr_title:
        _add("title", None, cr_title)

    # Authors (compare ordered last names — first name formats vary too much)
    bib_author = entry.get("author", "")
    cr_authors = crossref.get("authors", [])
    if not bib_author and cr_authors:
        _add("author", None, " and ".join(cr_authors))
    elif bib_author and cr_authors:
        bib_names = _normalize_author_list(bib_author)
        cr_names = _crossref_author_last_names(cr_authors)
        # Compare the overlapping prefix — flag if it disagrees or if
        # either side has authors the other doesn't.
        n = min(len(bib_names), len(cr_names))
        prefix_matches = bib_names[:n] == cr_names[:n]
        if not prefix_matches:
            # The authors they both list don't agree (wrong names or order)
            _add("author", bib_author, " and ".join(cr_authors))
        elif len(bib_names) != len(cr_names):
            # One side has more authors than the other — let the agent decide
            _add("author", bib_author, " and ".join(cr_authors))

    # Year
    bib_year = entry.get("year", "").strip()
    cr_year = crossref.get("year") or ""
    if bib_year and cr_year and bib_year != cr_year:
        _add("year", bib_year, cr_year)
    elif not bib_year and cr_year:
        _add("year", None, cr_year)

    # Journal / booktitle — use the actual field name from the entry
    bib_venue_field = _venue_field_for_entry(entry)
    bib_venue = entry.get(bib_venue_field, "")
    cr_venue = crossref.get("journal") or ""
    if not bib_venue and cr_venue:
        _add(bib_venue_field, None, cr_venue)
    elif bib_venue and cr_venue:
        is_preprint = re.search(r"\b(arxiv|biorxiv|chemrxiv|medrxiv)\b", bib_venue, re.IGNORECASE)
        if is_preprint:
            # Preprint upgraded to published venue
            if not re.search(r"\b(arxiv|biorxiv|chemrxiv|medrxiv)\b", cr_venue, re.IGNORECASE):
                _add(bib_venue_field, bib_venue, cr_venue)
        else:
            # Non-preprint venue mismatch
            if normalize_title(bib_venue) != normalize_title(cr_venue):
                _add(bib_venue_field, bib_venue, cr_venue)

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

    # DOI
    bib_doi = entry.get("doi", "").strip()
    cr_doi = crossref.get("doi") or ""
    if bib_doi and cr_doi:
        if normalize_doi(bib_doi) != normalize_doi(cr_doi):
            _add("doi", bib_doi, cr_doi)

    # Entry type
    cr_type = crossref.get("type") or ""
    bib_type = entry.get("entry_type", "")
    if cr_type and bib_type and cr_type != bib_type:
        _add("entry_type", bib_type, cr_type)

    return mismatches


def lookup_and_compare(entry: dict, timeout: int = 10) -> dict:
    """Fetch CrossRef data for an entry and compare fields.

    Returns a dict with: key, versions (list of CrossRef matches with
    mismatches), error (if any).
    """
    key = entry["key"]
    result = {"key": key, "versions": [], "error": None}

    title = entry.get("title", "")
    doi = entry.get("doi", "").strip()
    if not title and not doi:
        result["error"] = "No DOI or title to search"
        return result

    # Collect CrossRef results from all strategies, then deduplicate.
    matches = []
    seen_dois = set()
    last_error = None
    bib_title_norm = normalize_title(title)

    def _add(item):
        item_doi = item.get("doi")
        if item_doi and item_doi in seen_dois:
            return
        if item_doi:
            seen_dois.add(item_doi)
        matches.append(item)

    def _search(search_fn, query):
        nonlocal last_error
        cr = search_fn(query, rows=3, timeout=timeout)
        if "error" in cr:
            last_error = cr["error"]
            return
        for item in cr.get("results", []):
            if normalize_title(item.get("title") or "") == bib_title_norm:
                _add(item)

    if title:
        _search(search_title, title)
        _search(search_bibliographic, title)

    if doi:
        cr = fetch_doi(normalize_doi(doi), timeout=timeout)
        if "error" in cr:
            last_error = cr["error"]
        else:
            _add(cr)

    if not matches:
        result["error"] = last_error or "No exact title match in CrossRef results"
        return result

    result["versions"] = [
        {
            "type": item.get("type"),
            "year": item.get("year"),
            "journal": item.get("journal"),
            "doi": item.get("doi"),
            "url": item.get("url"),
            "mismatches": compare_entry(entry, item),
        }
        for item in matches
    ]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare BibTeX entries against CrossRef metadata")
    parser.add_argument("bibfile", help="Path to .bib file")
    parser.add_argument("--key", help="Only compare this citation key")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds")
    args = parser.parse_args()

    try:
        with open(args.bibfile, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.bibfile}", file=sys.stderr)
        sys.exit(1)

    try:
        entries = parse_bib_entries(text)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
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
