#!/usr/bin/env python3
"""Detect duplicate entries in a BibTeX file.

Usage: python3 duplicates.py <file.bib>

Outputs a JSON array of duplicate pairs to stdout.
"""

import json
import re
import sys
import unicodedata

def _is_escaped(text, pos):
    """Return True if the character at *pos* is preceded by a backslash."""
    return pos > 0 and text[pos - 1] == "\\"


def _remove_special_blocks(text):
    """Replace @string, @preamble, @comment blocks with whitespace."""
    skip_types = {"string", "preamble", "comment"}
    result = list(text)
    for m in re.finditer(r"@(\w+)\s*\{", text):
        if m.group(1).lower() not in skip_types:
            continue
        # Blank out from '@' through the matching '}'
        start = m.start()
        pos = m.end()
        depth = 1
        while pos < len(text) and depth > 0:
            if text[pos] == "{" and not _is_escaped(text, pos):
                depth += 1
            elif text[pos] == "}" and not _is_escaped(text, pos):
                depth -= 1
            pos += 1
        for i in range(start, pos):
            result[i] = " "
    return "".join(result)

def parse_bib_entries(text):
    """Parse BibTeX entries from *text*, returning a list of dicts.

    Each dict has keys: 'entry_type', 'key', and field names (lowercase).
    Handles nested braces in field values.
    Skips @string, @preamble, and @comment blocks.
    """
    entries = []

    # First, blank out @string, @preamble, @comment blocks so their contents
    # (including any nested @-entries) are not picked up.
    text = _remove_special_blocks(text)

    # Strip BibTeX comment lines (lines starting with %) so that
    # commented-out entries from bibtidy's own output are not parsed.
    text = re.sub(r"(?m)^[ \t]*%.*$", "", text)

    # Find every @type{ pattern
    entry_starts = list(re.finditer(r"@(\w+)\s*\{", text))

    for idx, m in enumerate(entry_starts):
        entry_type = m.group(1).lower()

        # Find the matching closing brace by counting nesting
        start = m.end()  # position right after the opening '{'
        depth = 1
        pos = start
        while pos < len(text) and depth > 0:
            if text[pos] == "{" and not _is_escaped(text, pos):
                depth += 1
            elif text[pos] == "}" and not _is_escaped(text, pos):
                depth -= 1
            pos += 1

        if depth != 0:
            continue  # malformed entry, skip

        body = text[start : pos - 1]  # content between outer braces

        # The citation key is everything up to the first comma
        comma = body.find(",")
        if comma == -1:
            continue
        key = body[:comma].strip()
        fields_text = body[comma + 1 :]

        fields = _parse_fields(fields_text)
        entry = {"entry_type": entry_type, "key": key}
        entry.update(fields)
        entries.append(entry)

    return entries

def _parse_fields(text):
    """Extract field = value pairs from the body of a BibTeX entry."""
    fields = {}
    pos = 0
    length = len(text)

    while pos < length:
        # Skip whitespace and commas
        while pos < length and text[pos] in " \t\n\r,":
            pos += 1
        if pos >= length:
            break

        # Match field name
        m = re.match(r"([A-Za-z_][\w-]*)\s*=\s*", text[pos:])
        if not m:
            # Skip to next comma or end
            next_comma = text.find(",", pos)
            pos = next_comma + 1 if next_comma != -1 else length
            continue

        field_name = m.group(1).lower()
        pos += m.end()

        # Now read the value — could be {…}, "…", or a bare token/number
        value, pos = _read_value(text, pos)
        fields[field_name] = value

    return fields

def _read_value(text, pos):
    """Read a single BibTeX field value starting at *pos*.

    Handles brace-delimited, quote-delimited, and bare values,
    as well as concatenation with #.
    """
    length = len(text)
    parts = []

    while pos < length:
        # Skip whitespace
        while pos < length and text[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break

        if text[pos] == "{":
            val, pos = _read_braced(text, pos)
            parts.append(val)
        elif text[pos] == '"':
            val, pos = _read_quoted(text, pos)
            parts.append(val)
        else:
            # Bare token or number
            m = re.match(r"[\w.-]+", text[pos:])
            if m:
                parts.append(m.group(0))
                pos += m.end()
            else:
                break

        # Check for concatenation
        while pos < length and text[pos] in " \t\n\r":
            pos += 1
        if pos < length and text[pos] == "#":
            pos += 1
        else:
            break

    return " ".join(parts), pos

def _read_braced(text, pos):
    """Read a brace-delimited value starting at *pos* (which must be '{')."""
    if text[pos] != "{":
        raise ValueError(f"Expected '{{' at position {pos}, got {text[pos]!r}")
    depth = 1
    start = pos + 1
    pos += 1
    while pos < len(text) and depth > 0:
        if text[pos] == "{" and not _is_escaped(text, pos):
            depth += 1
        elif text[pos] == "}" and not _is_escaped(text, pos):
            depth -= 1
        pos += 1
    return text[start : pos - 1], pos

def _read_quoted(text, pos):
    """Read a quote-delimited value starting at *pos* (which must be '"')."""
    if text[pos] != '"':
        raise ValueError(f"Expected '\"' at position {pos}, got {text[pos]!r}")
    pos += 1
    start = pos
    depth = 0
    while pos < len(text):
        if text[pos] == "{" and not _is_escaped(text, pos):
            depth += 1
        elif text[pos] == "}" and not _is_escaped(text, pos):
            depth -= 1
        elif text[pos] == '"' and depth == 0:
            val = text[start:pos]
            pos += 1
            return val, pos
        pos += 1
    return text[start:pos], pos

_LATEX_CMD_RE = re.compile(r"\\(?:textbf|textit|emph|textsc|textrm|textsf|texttt|mathit|mathrm|mathbf)\b\s*")

def normalize_title(title):
    """Normalize a title for fuzzy comparison.

    Lowercase, strip braces, strip common LaTeX commands, collapse whitespace,
    remove punctuation.
    """
    t = title.lower()
    # Remove common LaTeX commands (keep their arguments)
    t = _LATEX_CMD_RE.sub("", t)
    # Remove remaining backslash commands like \' \~ etc.
    t = re.sub(r"\\[a-zA-Z]+\s*", "", t)
    t = re.sub(r"\\.", "", t)
    # Strip braces
    t = t.replace("{", "").replace("}", "")
    # Normalize Unicode accents (e.g., é → e) so LaTeX \'{e} and UTF-8 é match
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    # Remove punctuation (keep alphanumeric and spaces)
    t = re.sub(r"[^a-z0-9\s]", "", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t

_PREPRINT_RE = re.compile(r"\b(arxiv|biorxiv|chemrxiv)\b", re.IGNORECASE)

def is_preprint(entry):
    """Return True if the entry looks like a preprint."""
    for field in ("journal", "note", "howpublished"):
        if _PREPRINT_RE.search(entry.get(field, "")):
            return True
    if entry.get("archiveprefix", "").lower() in ("arxiv",):
        return True
    if entry.get("eprint", ""):
        # eprint field is commonly used for arXiv IDs
        return bool(re.match(r"\d{4}\.\d+", entry.get("eprint", "")))
    return False

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
    a_names = {_normalize_author_last(n) for n in a_raw.split(" and ")}
    b_names = {_normalize_author_last(n) for n in b_raw.split(" and ")}
    # Remove empty strings from splitting artifacts
    a_names.discard("")
    b_names.discard("")
    return bool(a_names & b_names)

def find_duplicates(entries):
    """Return a list of duplicate-pair dicts."""
    duplicates = []

    # Index helpers
    keys_seen = {}       # key -> list of indices
    dois_seen = {}       # normalised doi -> list of indices
    titles_seen = {}     # normalised title -> list of indices

    for i, entry in enumerate(entries):
        key = entry["key"]

        # -- same key --
        keys_seen.setdefault(key, []).append(i)

        # -- same doi (strip https://doi.org/ prefix before indexing) --
        doi = re.sub(r"^https?://doi\.org/", "", entry.get("doi", "").strip(), flags=re.IGNORECASE).lower()
        if doi:
            dois_seen.setdefault(doi, []).append(i)

        # -- title index --
        raw_title = entry.get("title", "")
        norm = normalize_title(raw_title)
        if norm:
            titles_seen.setdefault(norm, []).append(i)

    # Collect same-key duplicates
    for key, idxs in keys_seen.items():
        if len(idxs) > 1:
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    duplicates.append({
                        "type": "same_key",
                        "key1": entries[idxs[a]]["key"],
                        "key2": entries[idxs[b]]["key"],
                        "detail": f"Duplicate citation key: {key}",
                    })

    # Collect same-doi duplicates (only between *different* keys)
    for doi, idxs in dois_seen.items():
        if len(idxs) > 1:
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    ea, eb = entries[idxs[a]], entries[idxs[b]]
                    if ea["key"] != eb["key"]:
                        duplicates.append({
                            "type": "same_doi",
                            "key1": ea["key"],
                            "key2": eb["key"],
                            "detail": f"Same DOI: {doi}",
                        })

    # Collect same-title duplicates and preprint+published pairs
    for norm_title, idxs in titles_seen.items():
        if len(idxs) > 1:
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    ea, eb = entries[idxs[a]], entries[idxs[b]]
                    if ea["key"] == eb["key"]:
                        continue  # already caught by same_key

                    # Check preprint+published
                    a_pre = is_preprint(ea)
                    b_pre = is_preprint(eb)
                    ja = ea.get("journal", "") or ea.get("booktitle", "")
                    jb = eb.get("journal", "") or eb.get("booktitle", "")

                    if (a_pre and not b_pre and jb) or (b_pre and not a_pre and ja):
                        pre_key = ea["key"] if a_pre else eb["key"]
                        pub_key = eb["key"] if a_pre else ea["key"]
                        duplicates.append({
                            "type": "preprint_published",
                            "key1": pre_key,
                            "key2": pub_key,
                            "detail": f"Preprint and published version of: {norm_title}",
                        })
                    else:
                        # Require at least one shared author to reduce false
                        # positives on generic titles like "A Survey of …"
                        if _share_author(ea, eb):
                            duplicates.append({
                                "type": "same_title",
                                "key1": ea["key"],
                                "key2": eb["key"],
                                "detail": f"Same normalised title: {norm_title}",
                            })

    return duplicates

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file.bib>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    entries = parse_bib_entries(text)
    dups = find_duplicates(entries)
    print(json.dumps(dups, indent=2))

if __name__ == "__main__":
    main()
