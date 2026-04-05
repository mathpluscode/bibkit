#!/usr/bin/env python3
"""Detect duplicate entries in a BibTeX file.

Usage: python3 duplicates.py <file.bib>

Outputs a JSON array of duplicate pairs to stdout.
"""

import json
import re
import sys
import unicodedata

from parser import comment_out, ensure_brace_only_entries, find_entry_spans, parse_bib_entries

_DOI_URL_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
_AUTHOR_SPLIT_RE = re.compile(r"\s+and\s+")
_PREPRINT_VENUE_RE = re.compile(r"\b(arxiv|biorxiv|chemrxiv|medrxiv)\b", re.IGNORECASE)


def normalize_doi(doi):
    """Normalize DOI strings for comparison and indexing."""
    return _DOI_URL_RE.sub("", doi.strip()).lower()


def split_bibtex_authors(authors_str):
    """Split a BibTeX author field on the 'and' separator."""
    authors_str = authors_str.strip()
    if not authors_str:
        return []
    return [name for name in _AUTHOR_SPLIT_RE.split(authors_str) if name.strip()]


def normalize_title(title):
    """Normalize a title for fuzzy comparison."""
    t = title.lower()
    t = re.sub(r"\\[a-zA-Z]+\s*", "", t)
    t = re.sub(r"\\.", "", t)
    t = t.replace("{", "").replace("}", "")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalize_author_last(name):
    """Extract a lowercase last name from 'Last, First' or 'First Last'."""
    name = name.strip()
    if "," in name:
        return name.split(",")[0].strip().lower()
    parts = name.split()
    return parts[-1].lower() if parts else ""


def _share_author(ea, eb):
    """Return True if two entries share at least one author last name."""
    a_raw = ea.get("author", "")
    b_raw = eb.get("author", "")
    if not a_raw or not b_raw:
        return False
    a_names = {_normalize_author_last(n) for n in split_bibtex_authors(a_raw)}
    b_names = {_normalize_author_last(n) for n in split_bibtex_authors(b_raw)}
    a_names.discard("")
    b_names.discard("")
    return bool(a_names & b_names)


def _first_author_last(entry):
    """Return the lowercase last name of the first author, if present."""
    authors = split_bibtex_authors(entry.get("author", ""))
    if not authors:
        return ""
    return _normalize_author_last(authors[0])


def _entry_venue(entry):
    """Return the venue-like field used to classify preprints."""
    return entry.get("journal", "") or entry.get("booktitle", "")


def _is_preprint(entry):
    """Return True for arXiv/bioRxiv/medRxiv/chemRxiv-style entries."""
    venue = _entry_venue(entry)
    return entry.get("entry_type") == "preprint" or bool(_PREPRINT_VENUE_RE.search(venue))


def _title_keywords(title):
    """Return significant normalized title words for fuzzy duplicate checks."""
    return {word for word in normalize_title(title).split() if len(word) >= 6}


def _parse_year(entry):
    """Return the entry year as an int when it looks usable."""
    try:
        return int((entry.get("year") or "").strip())
    except ValueError:
        return None


def _is_preprint_published_pair(ea, eb):
    """Heuristic for retitled preprint/published pairs with the same lead author."""
    if ea["key"] == eb["key"] or _is_preprint(ea) == _is_preprint(eb):
        return False
    first_a = _first_author_last(ea)
    first_b = _first_author_last(eb)
    if not first_a or first_a != first_b:
        return False

    year_a = _parse_year(ea)
    year_b = _parse_year(eb)
    if year_a is not None and year_b is not None and abs(year_a - year_b) > 2:
        return False

    return len(_title_keywords(ea.get("title", "")) & _title_keywords(eb.get("title", ""))) >= 3


def _normalize_field_value(value):
    """Normalize a field value for exact comparison (collapse whitespace)."""
    return re.sub(r"\s+", " ", value.strip())


def _entry_fingerprint(entry):
    """Return a hashable fingerprint for exact duplicate detection."""
    fields = {k: _normalize_field_value(v) for k, v in entry.items() if k not in ("key", "entry_type")}
    return (entry["key"], entry["entry_type"], tuple(sorted(fields.items())))


def remove_exact_duplicates(text):
    """Comment out exact duplicate entries in bib text.

    Returns (modified_text, count_removed).
    """
    ensure_brace_only_entries(text)
    spans = find_entry_spans(text)
    seen = {}
    to_remove = []

    for i, (key, start, end) in enumerate(spans):
        raw = text[start:end]
        parsed = parse_bib_entries(raw)
        if not parsed:
            continue
        fp = _entry_fingerprint(parsed[0])
        if fp in seen:
            to_remove.append((start, end))
        else:
            seen[fp] = i

    for start, end in sorted(to_remove, reverse=True):
        raw = text[start:end]
        commented = comment_out(raw)
        text = text[:start] + f"% bibtidy: exact duplicate, commented out\n{commented}" + text[end:]

    return text, len(to_remove)


def find_duplicates(entries):
    """Return a list of duplicate-pair dicts."""
    duplicates = []
    keys_seen = {}
    dois_seen = {}
    titles_seen = {}
    seen_pairs = set()

    def _add(dup_type, a, b, detail):
        pair = (a, b)
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        duplicates.append({"type": dup_type, "key1": entries[a]["key"], "key2": entries[b]["key"], "detail": detail})

    for i, entry in enumerate(entries):
        key = entry["key"]
        keys_seen.setdefault(key, []).append(i)

        doi = normalize_doi(entry.get("doi", ""))
        if doi:
            dois_seen.setdefault(doi, []).append(i)

        norm = normalize_title(entry.get("title", ""))
        if norm:
            titles_seen.setdefault(norm, []).append(i)

    def _pairs(idxs):
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                yield idxs[a], idxs[b]

    for key, idxs in keys_seen.items():
        if len(idxs) > 1:
            for a, b in _pairs(idxs):
                _add("same_key", a, b, f"Duplicate citation key: {key}")

    for doi, idxs in dois_seen.items():
        if len(idxs) > 1:
            for a, b in _pairs(idxs):
                if entries[a]["key"] != entries[b]["key"]:
                    _add("same_doi", a, b, f"Same DOI: {doi}")

    for norm_title, idxs in titles_seen.items():
        if len(idxs) > 1:
            for a, b in _pairs(idxs):
                ea, eb = entries[a], entries[b]
                if ea["key"] == eb["key"]:
                    continue
                if _share_author(ea, eb):
                    _add("same_title", a, b, f"Same normalised title: {norm_title}")

    for a in range(len(entries)):
        for b in range(a + 1, len(entries)):
            if _is_preprint_published_pair(entries[a], entries[b]):
                _add("preprint_published", a, b, "Likely preprint/published pair")

    return duplicates


def main():
    if len(sys.argv) == 3 and sys.argv[2] == "--exact":
        path = sys.argv[1]
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        try:
            result, count = remove_exact_duplicates(text)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        if count:
            with open(path, "w", encoding="utf-8") as f:
                f.write(result)
        print(f"Removed {count} exact duplicate(s)")
        return

    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file.bib>", file=sys.stderr)
        print(f"       {sys.argv[0]} <file.bib> --exact", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        entries = parse_bib_entries(text)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    dups = find_duplicates(entries)
    print(json.dumps(dups, indent=2))


if __name__ == "__main__":
    main()
