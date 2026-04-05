#!/usr/bin/env python3
"""Shared BibTeX parsing and source-navigation helpers."""

import re


def comment_out(text):
    """Prefix every line with ``% ``."""
    return "\n".join("% " + line for line in text.split("\n"))


PAREN_STYLE_ERROR = (
    "Parenthesized BibTeX blocks like @article(...) are not supported; "
    "please convert them to brace style like @article{...} first."
)
SPECIAL_TYPES = {"string", "preamble", "comment"}


def is_escaped(text, pos):
    """Return True if the character at *pos* is preceded by a backslash."""
    return pos > 0 and text[pos - 1] == "\\"


def skip_braces(text, pos):
    """Advance from just after an opening '{' to just after its match."""
    depth = 1
    while pos < len(text):
        ch = text[pos]
        if ch == "{" and not is_escaped(text, pos):
            depth += 1
        elif ch == "}" and not is_escaped(text, pos):
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    return None


def remove_special_blocks(text):
    """Replace @string, @preamble, @comment blocks with whitespace."""
    spans = []
    for entry_match in re.finditer(r"@(\w+)\s*\{", text):
        if entry_match.group(1).lower() not in SPECIAL_TYPES:
            continue
        end = skip_braces(text, entry_match.end())
        if end is not None:
            spans.append((entry_match.start(), end))
    for start, end in reversed(spans):
        block = text[start:end]
        text = text[:start] + re.sub(r"[^\n]", " ", block) + text[end:]
    return text


def ensure_brace_only_entries(text):
    """Raise if active file content uses parenthesized BibTeX syntax."""
    cleaned = remove_special_blocks(text)
    cleaned = re.sub(r"(?m)^[ \t]*%.*$", "", cleaned)
    entry_match = re.search(r"(?m)^[ \t]*@(\w+)\s*\(", cleaned)
    if not entry_match:
        return
    line = cleaned.count("\n", 0, entry_match.start()) + 1
    raise ValueError(f"{PAREN_STYLE_ERROR} Found '@{entry_match.group(1)}(' on line {line}.")


def _read_braced(text, pos):
    """Read a brace-delimited value starting at '{'."""
    start = pos + 1
    end = skip_braces(text, start)
    if end is None:
        return text[start:], len(text)
    return text[start : end - 1], end


def _read_quoted(text, pos):
    """Read a quote-delimited value starting at '"'."""
    pos += 1
    start = pos
    depth = 0
    while pos < len(text):
        ch = text[pos]
        if ch == "{" and not is_escaped(text, pos):
            depth += 1
        elif ch == "}" and not is_escaped(text, pos):
            depth -= 1
        elif ch == '"' and depth == 0:
            return text[start:pos], pos + 1
        pos += 1
    return text[start:pos], pos


def _read_value(text, pos):
    """Read a BibTeX field value (braced, quoted, bare, or # concatenation)."""
    parts = []
    while pos < len(text):
        while pos < len(text) and text[pos] in " \t\n\r":
            pos += 1
        if pos >= len(text):
            break
        if text[pos] == "{":
            value, pos = _read_braced(text, pos)
            parts.append(value)
        elif text[pos] == '"':
            value, pos = _read_quoted(text, pos)
            parts.append(value)
        else:
            token_match = re.match(r"[\w.-]+", text[pos:])
            if not token_match:
                break
            parts.append(token_match.group(0))
            pos += token_match.end()
        while pos < len(text) and text[pos] in " \t\n\r":
            pos += 1
        if pos < len(text) and text[pos] == "#":
            pos += 1
        else:
            break
    return " ".join(parts), pos


def _parse_fields(text):
    """Extract field = value pairs from the body of a BibTeX entry."""
    fields = {}
    pos = 0
    while pos < len(text):
        while pos < len(text) and text[pos] in " \t\n\r,":
            pos += 1
        if pos >= len(text):
            break
        field_match = re.match(r"([A-Za-z_][\w-]*)\s*=\s*", text[pos:])
        if not field_match:
            next_comma = text.find(",", pos)
            pos = next_comma + 1 if next_comma != -1 else len(text)
            continue
        field_name = field_match.group(1).lower()
        pos += field_match.end()
        value, pos = _read_value(text, pos)
        fields[field_name] = value
    return fields


def parse_bib_entries(text):
    """Parse BibTeX entries from *text* into dicts."""
    ensure_brace_only_entries(text)
    cleaned = remove_special_blocks(text)
    cleaned = re.sub(r"(?m)^[ \t]*%.*$", "", cleaned)

    entries = []
    for entry_match in re.finditer(r"@(\w+)\s*\{", cleaned):
        end = skip_braces(cleaned, entry_match.end())
        if end is None:
            continue
        body = cleaned[entry_match.end() : end - 1]
        comma = body.find(",")
        if comma == -1:
            continue
        key = body[:comma].strip()
        fields = _parse_fields(body[comma + 1 :])
        entries.append({"entry_type": entry_match.group(1).lower(), "key": key, **fields})
    return entries


def find_entry_spans(text):
    """Return (key, start, end) spans for active BibTeX entries."""
    cleaned = remove_special_blocks(text)
    cleaned = re.sub(r"(?m)^[ \t]*%.*$", lambda m: " " * len(m.group()), cleaned)

    spans = []
    for entry_match in re.finditer(r"@(\w+)\s*\{", cleaned):
        if entry_match.group(1).lower() in SPECIAL_TYPES:
            continue
        end = skip_braces(cleaned, entry_match.end())
        if end is None:
            continue
        body = text[entry_match.end() : end - 1]
        comma = body.find(",")
        if comma == -1:
            continue
        key = body[:comma].strip()
        spans.append((key, entry_match.start(), end))
    return spans
