#!/usr/bin/env python3
"""Apply bibtidy patches to a BibTeX file.

Reads a .bib file and a JSON patch list, applies edits in place.

Usage:
    python3 edit.py <file.bib> <patches.json>
    python3 edit.py <file.bib> -          # read patches from stdin

Patch format (JSON array of objects):
    {
        "key":          "citation_key",
        "action":       "fix" | "not_found" | "duplicate",
        "urls":         ["https://...", ...],    # fix only, sorted & deduplicated
        "explanation":  "what changed",          # fix only
        "fields":       {"title": "New", ...},   # fix only (null = remove)
        "entry_type":   "inproceedings",         # fix, optional (change type)
        "duplicate_of": "other_key"              # duplicate only
    }
"""

import json
import re
import sys

from parser import comment_out, find_entry_spans, parse_bib_entries

_VENUE_SWAP = {"journal": "booktitle", "booktitle": "journal"}


def _extract_field_order(raw_entry):
    """Return field names in source order from raw BibTeX entry text."""
    fields = []
    for line in raw_entry.split("\n")[1:]:
        m = re.match(r"\s*([A-Za-z_][\w-]*)\s*=", line)
        if m:
            fields.append(m.group(1).lower())
    return fields


def _compute_field_order(original_order, final_fields):
    """Decide output field order, handling venue swaps."""
    order = []
    used = set()

    for f in original_order:
        if f in final_fields:
            order.append(f)
            used.add(f)
        elif f in _VENUE_SWAP:
            replacement = _VENUE_SWAP[f]
            if replacement in final_fields and replacement not in used:
                order.append(replacement)
                used.add(replacement)

    for f in final_fields:
        if f not in used:
            order.append(f)

    return order


def _build_entry(entry_type, key, fields, field_order):
    """Format a BibTeX entry from structured data."""
    lines = [f"@{entry_type}{{{key},"]
    for i, f in enumerate(field_order):
        val = fields[f]
        comma = "," if i < len(field_order) - 1 else ""
        lines.append(f"  {f}={{{val}}}{comma}")
    lines.append("}")
    return "\n".join(lines)


def apply_patch(raw_entry, parsed_entry, patch):
    """Return replacement text for a single entry.

    *raw_entry* is the original text (``@type{key, ...}``).
    *parsed_entry* is the dict from ``parse_bib_entries``.
    *patch* is one element of the patch list.
    """
    action = patch["action"]

    if action == "not_found":
        commented = comment_out(raw_entry)
        return (
            "% bibtidy: NOT FOUND \u2014 no matching paper on CrossRef "
            "or web search; verify this reference exists\n" + commented
        )

    if action == "duplicate":
        dup_of = patch["duplicate_of"]
        return f"% bibtidy: DUPLICATE of {dup_of} \u2014 consider removing\n" + raw_entry

    if action != "fix":
        raise ValueError(f"Unknown action: {action}")

    # --- action == "fix" ---
    entry_type = patch.get("entry_type", parsed_entry["entry_type"])
    key = parsed_entry["key"]

    # Build final field dict
    original_order = _extract_field_order(raw_entry)
    fields = {}
    for f in original_order:
        if f in parsed_entry:
            fields[f] = parsed_entry[f]

    for f, val in patch.get("fields", {}).items():
        if val is None:
            fields.pop(f, None)
        else:
            fields[f] = val

    field_order = _compute_field_order(original_order, fields)

    # Assemble replacement
    commented = comment_out(raw_entry)
    meta = []
    for url in sorted(set(patch.get("urls", []))):
        meta.append(f"% bibtidy: {url}")
    if patch.get("explanation"):
        meta.append(f"% bibtidy: {patch['explanation']}")

    corrected = _build_entry(entry_type, key, fields, field_order)
    return "\n".join([commented] + meta + [corrected])


def apply_patches(text, patches):
    """Apply all patches to the .bib text, returning (modified text, applied keys)."""
    spans = find_entry_spans(text)

    patch_by_key = {p["key"]: p for p in patches}

    applied_keys = set()

    for key, start, end in sorted(spans, key=lambda x: x[1], reverse=True):
        if key not in patch_by_key:
            continue
        raw = text[start:end]
        parsed = parse_bib_entries(raw)
        if not parsed:
            continue
        replacement = apply_patch(raw, parsed[0], patch_by_key[key])
        text = text[:start] + replacement + text[end:]
        applied_keys.add(key)

    skipped = [k for k in patch_by_key if k not in applied_keys]
    if skipped:
        print(f"Warning: patches skipped (key not in .bib): {', '.join(skipped)}", file=sys.stderr)

    return text, applied_keys


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <file.bib> <patches.json>")
        sys.exit(1)

    bib_path = sys.argv[1]
    patch_arg = sys.argv[2]

    with open(bib_path, encoding="utf-8") as f:
        text = f.read()

    if patch_arg == "-":
        patches = json.load(sys.stdin)
    else:
        with open(patch_arg, encoding="utf-8") as f:
            patches = json.load(f)

    result, applied_keys = apply_patches(text, patches)

    with open(bib_path, "w", encoding="utf-8") as f:
        f.write(result)

    counts = {"fix": 0, "not_found": 0, "duplicate": 0}
    for p in patches:
        if p["key"] not in applied_keys:
            continue
        a = p.get("action", "")
        if a in counts:
            counts[a] += 1
    total = sum(counts.values())
    print(
        f"Applied {total} patches: "
        f"{counts['fix']} fixed, "
        f"{counts['not_found']} not found, "
        f"{counts['duplicate']} duplicates"
    )


if __name__ == "__main__":
    main()
