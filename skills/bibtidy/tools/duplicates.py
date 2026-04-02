#!/usr/bin/env python3
"""Detect duplicate entries in a BibTeX file.

Usage: python3 duplicates.py <file.bib>

Outputs a JSON array of duplicate pairs to stdout.
"""

import json
import re
import sys
import unicodedata

PAREN_STYLE_ERROR = (
    "Parenthesized BibTeX blocks like @article(...) are not supported; "
    "please convert them to brace style like @article{...} first."
)
_DOI_URL_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
_AUTHOR_SPLIT_RE = re.compile(r"\s+and\s+")


def ensure_brace_only_entries(text):
    """Raise if active file content uses parenthesized BibTeX syntax."""
    text = remove_special_blocks(text)
    text = re.sub(r"(?m)^[ \t]*%.*$", "", text)
    match = re.search(r"(?m)^[ \t]*@(\w+)\s*\(", text)
    if not match:
        return
    line = text.count("\n", 0, match.start()) + 1
    raise ValueError(f"{PAREN_STYLE_ERROR} Found '@{match.group(1)}(' on line {line}.")


def is_escaped(text, pos):
    """Return True if the character at *pos* is preceded by a backslash."""
    return pos > 0 and text[pos - 1] == "\\"


def _find_block_end(text, start):
    """Return the index just after a balanced BibTeX block, or None."""
    depth = 1
    pos = start
    while pos < len(text):
        if text[pos] == "{" and not is_escaped(text, pos):
            depth += 1
        elif text[pos] == "}" and not is_escaped(text, pos):
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    return None


def remove_special_blocks(text):
    """Replace @string, @preamble, @comment blocks with whitespace (preserving newlines)."""
    skip_types = {"string", "preamble", "comment"}
    spans = []
    for m in re.finditer(r"@(\w+)\s*\{", text):
        if m.group(1).lower() not in skip_types:
            continue
        end = _find_block_end(text, m.end())
        if end is not None:
            spans.append((m.start(), end))
    # Replace spans in reverse so offsets stay valid.
    for start, end in reversed(spans):
        block = text[start:end]
        text = text[:start] + re.sub(r"[^\n]", " ", block) + text[end:]
    return text


def normalize_doi(doi):
    """Normalize DOI strings for comparison and indexing."""
    return _DOI_URL_RE.sub("", doi.strip()).lower()


def split_bibtex_authors(authors_str):
    """Split a BibTeX author field on the 'and' separator."""
    authors_str = authors_str.strip()
    if not authors_str:
        return []
    return [name for name in _AUTHOR_SPLIT_RE.split(authors_str) if name.strip()]


def parse_bib_entries(text):
    """Parse BibTeX entries from *text*, returning a list of dicts.

    Each dict has keys: 'entry_type', 'key', and field names (lowercase).
    Handles nested braces in field values.
    Skips @string, @preamble, and @comment blocks.
    """
    entries = []
    ensure_brace_only_entries(text)

    # First, blank out @string, @preamble, @comment blocks so their contents
    # (including any nested @-entries) are not picked up.
    text = remove_special_blocks(text)

    # Strip BibTeX comment lines (lines starting with %) so that
    # commented-out entries from bibtidy's own output are not parsed.
    text = re.sub(r"(?m)^[ \t]*%.*$", "", text)

    # Find every @type{ pattern
    entry_starts = list(re.finditer(r"@(\w+)\s*\{", text))

    for m in entry_starts:
        entry_type = m.group(1).lower()

        start = m.end()  # position right after the opening delimiter
        pos = _find_block_end(text, start)
        if pos is None:
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
        if text[pos] == "{" and not is_escaped(text, pos):
            depth += 1
        elif text[pos] == "}" and not is_escaped(text, pos):
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
        if text[pos] == "{" and not is_escaped(text, pos):
            depth += 1
        elif text[pos] == "}" and not is_escaped(text, pos):
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
    # Remove empty strings from splitting artifacts
    a_names.discard("")
    b_names.discard("")
    return bool(a_names & b_names)


def find_duplicates(entries):
    """Return a list of duplicate-pair dicts."""
    duplicates = []

    # Index helpers
    keys_seen = {}  # key -> list of indices
    dois_seen = {}  # normalised doi -> list of indices
    titles_seen = {}  # normalised title -> list of indices

    for i, entry in enumerate(entries):
        key = entry["key"]

        # Same key
        keys_seen.setdefault(key, []).append(i)

        # Same DOI
        doi = normalize_doi(entry.get("doi", ""))
        if doi:
            dois_seen.setdefault(doi, []).append(i)

        # Title index
        raw_title = entry.get("title", "")
        norm = normalize_title(raw_title)
        if norm:
            titles_seen.setdefault(norm, []).append(i)

    # Collect same-key duplicates
    for key, idxs in keys_seen.items():
        if len(idxs) > 1:
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    duplicates.append(
                        {
                            "type": "same_key",
                            "key1": entries[idxs[a]]["key"],
                            "key2": entries[idxs[b]]["key"],
                            "detail": f"Duplicate citation key: {key}",
                        }
                    )

    # Collect same-doi duplicates (only between *different* keys)
    for doi, idxs in dois_seen.items():
        if len(idxs) > 1:
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    ea, eb = entries[idxs[a]], entries[idxs[b]]
                    if ea["key"] != eb["key"]:
                        duplicates.append(
                            {"type": "same_doi", "key1": ea["key"], "key2": eb["key"], "detail": f"Same DOI: {doi}"}
                        )

    # Collect same-title duplicates
    for norm_title, idxs in titles_seen.items():
        if len(idxs) > 1:
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    ea, eb = entries[idxs[a]], entries[idxs[b]]
                    if ea["key"] == eb["key"]:
                        continue  # already caught by same_key
                    # Require at least one shared author to reduce false
                    # positives on generic titles like "A Survey of …"
                    if _share_author(ea, eb):
                        duplicates.append(
                            {
                                "type": "same_title",
                                "key1": ea["key"],
                                "key2": eb["key"],
                                "detail": f"Same normalised title: {norm_title}",
                            }
                        )

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

    try:
        entries = parse_bib_entries(text)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    dups = find_duplicates(entries)
    print(json.dumps(dups, indent=2))


if __name__ == "__main__":
    main()
