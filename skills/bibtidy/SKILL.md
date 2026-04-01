---
name: bibtidy
description: Use when the user wants to validate, check, or fix a BibTeX (.bib) reference file — wrong authors, stale arXiv preprints, incorrect metadata, duplicate entries, formatting issues
argument-hint: <path-to-file.bib>
allowed-tools: Bash(python3 *), Read, Edit, Agent, WebSearch
---

Validate and fix the BibTeX file at: $ARGUMENTS

If `$ARGUMENTS` is empty or the file does not exist, tell the user:
"Usage: /bibtidy <path-to-file.bib>"

You are a meticulous academic reference checker. Process the .bib file entry by entry, verifying each against external sources and fixing errors in-place.

## Quick Reference

| Tool | Command |
|------|---------|
| **Field comparison** | `python3 $TOOLS_DIR/compare.py <file.bib> [--key KEY]` |
| CrossRef DOI lookup | `python3 $TOOLS_DIR/crossref.py doi <DOI>` |
| CrossRef title search | `python3 $TOOLS_DIR/crossref.py search "<title>"` |
| Duplicate detection | `python3 $TOOLS_DIR/duplicates.py <file.bib>` |
| Format validation | `python3 $TOOLS_DIR/fmt.py <orig.bib> <modified.bib>` |
| Web verification | WebSearch tool (preferred) or CrossRef scripts (fallback) |

## Script Path Resolution

All bundled tools live in the `tools/` directory next to this SKILL.md, installed at `~/.claude/skills/bibtidy/tools`. Before running any tool, resolve the absolute path once:

```
TOOLS_DIR="$HOME/.claude/skills/bibtidy/tools"
if [ ! -f "$TOOLS_DIR/crossref.py" ]; then
  TOOLS_DIR="${CLAUDE_PLUGIN_ROOT}/skills/bibtidy/tools"
fi
```

Use `$TOOLS_DIR` in every invocation.

## Output Format for Changed Entries

The Edit tool replacement text MUST contain all four parts in order:

```
% @<type>{<key>,
%   <original field 1>,
%   <original field 2>,
%   ...
% }
% bibtidy: source <URL>
% bibtidy: <what changed>
@<type>{<key>,
  <corrected field 1>,
  <corrected field 2>,
  ...
}
```

- **Part 1** — entire original entry, every line prefixed by `% `. All lines, not just the first.
- **Part 2** — `% bibtidy: source ` followed by a URL. Must be exactly `% bibtidy: source https://...`.
- **Part 3** — `% bibtidy: ` followed by explanation of what changed.
- **Part 4** — corrected entry.

For unchanged entries, do NOT add any comments or URLs.

## Workflow

1. Read the .bib file, note the file path
2. Back up for format validation: `cp <file>.bib <file>.bib.orig`
3. Preserve `@string`, `@preamble`, `@comment` blocks verbatim
4. Run duplicate detection: `python3 $TOOLS_DIR/duplicates.py <file.bib>`
5. **Run field comparison**: `python3 $TOOLS_DIR/compare.py <file.bib>` — this programmatically compares every entry against CrossRef and returns exact field-level mismatches. Do NOT skip this step or rely on visual comparison alone.
6. **Verify with subagents in parallel** — for entries with mismatches OR errors from `compare.py`, dispatch subagents to gather source URLs and check for additional issues via WebSearch (see below). Entries where `compare.py` returned an error (e.g. "No exact title match") still need full verification — the subagent should search for the paper and check all fields. **Important: subagents MUST NOT override `compare.py` field values.** CrossRef is the authoritative source for metadata (pages, volume, number, etc.) because it receives data directly from publishers via DOI registration. When WebSearch finds a conflicting value (e.g. different page numbers on a conference website), always use the CrossRef value and add `% bibtidy: REVIEW` if desired — but do NOT keep the old value.
7. Apply fixes **sequentially** via Edit tool — do NOT rewrite the entire file. You MUST apply **every** mismatch reported by `compare.py` — do not skip any field (including `number`, `pages`, `volume`). Use the `crossref_value` exactly as given (do NOT rephrase, reformat, or partially apply it). For title mismatches on preprint→published upgrades, replace the entire title with the CrossRef title — do NOT try to edit parts of the old title. Never reject a CrossRef value because another source disagrees.
8. Run format validation; fix violations and re-run until clean
9. Delete backup: `rm <file>.bib.orig`
10. Print summary: total entries, verified, fixed, needs manual review

## Parallel Verification with Subagents

Use the Agent tool to verify multiple entries concurrently. This dramatically reduces wall-clock time (e.g., 7 entries: ~1 min parallel vs ~5 min sequential; 100 entries: ~3 min vs ~40 min).

**Step 1 — Dispatch verification agents:** For entries that `compare.py` flagged with mismatches OR returned errors, launch a subagent that:
- For mismatches: runs WebSearch to confirm the CrossRef data (especially for preprint upgrades and author changes)
- For errors (e.g. paper not found in CrossRef): runs WebSearch to verify **every** field from scratch — title, author, journal/booktitle, volume, number, pages, year. Do NOT skip number or other fields just because they look plausible.
- Returns a JSON summary: key, whether each mismatch is confirmed, source URL, any additional corrections found

**When CrossRef fails**, find the paper's official venue page via WebSearch. Many venues (JMLR, NeurIPS, CVPR, etc.) provide a downloadable `.bib` file — use WebFetch to grab it. An official `.bib` is the most reliable source: it has exact title, authors, volume, number, and pages with no guessing.

Launch all agents in a single message so they run concurrently. Group into batches of ~10 if there are many entries.

**Step 2 — Collect results:** Read each agent's returned summary.

**Step 3 — Apply edits sequentially:** Using the lookup results, apply Edit tool changes one entry at a time. Edits MUST be sequential (parallel edits to the same file cause conflicts).

**Example agent prompt:**
```
Verify this BibTeX entry against CrossRef. Return ONLY valid JSON with no markdown formatting or conversational text. Keys: "key", "needs_fix" (bool), "fixes" (list of changes), "source_url", "corrected_fields" (dict).

TOOLS_DIR="$HOME/.claude/skills/bibtidy/tools"

Entry:
@article{smith2020deep,
  title={Deep Learning for NLP},
  author={Smith, John},
  journal={arXiv preprint arXiv:2001.12345},
  year={2020}
}
```

## Duplicate Detection

```
python3 $TOOLS_DIR/duplicates.py <file.bib>
```

Returns JSON array of duplicate pairs (by key, DOI, title, or preprint+published). For each duplicate, add: `% bibtidy: DUPLICATE of <other_key> — consider removing`

## Per-Entry Checks

For each `@article`, `@inproceedings`, `@book`, etc.:

**1. Verify existence** — Search for `"<title>" <first author last name>`. If not found: `% bibtidy: NOT FOUND — verify manually`

**2. Cross-check metadata** — If DOI exists, fetch via `crossref.py doi <DOI>`. Otherwise `crossref.py search "<title>"`. Compare title, year, authors, journal, volume, pages.

**3. Check for published preprints** — If journal contains "arxiv"/"biorxiv"/"chemrxiv", search for published version. Update title, venue, year, volume, pages, entry type. Only update if confirmed via DOI or two independent sources.

**4. Apply fixes** — DOI URL prefix stripping, page hyphen fix (`-` → `--`), year whitespace, empty field removal, author corrections, venue/year/volume/pages corrections, preprint upgrades. Missing `pages` fields are NOT flagged — some venues (e.g. NeurIPS, ICLR) intentionally omit page numbers. Only mismatched pages (both sides have values that differ) are reported.

**Always apply the best-available fix.** If confidence is low (sources conflict, data incomplete, or only partial match), still apply the fix but add `% bibtidy: REVIEW — <reason>` explaining why it needs human attention.

## Saving Changes

- Use Edit tool for targeted replacements — not whole-file rewrites
- For large files (>30 entries), process in batches of ~15, reporting progress
- Verify entry count before and after — must match

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Missing `% bibtidy: source` URL | Every changed entry needs a source URL — use DOI URL or venue page |
| Incomplete commented original | Comment out ALL lines of the original, including closing `}` |
| Adding comments to unchanged entries | Only changed entries get bibtidy comments |
| Rewriting entire file | Use Edit tool for each entry individually |
| Deleting duplicate entries | Flag with comment only — never delete |
| Losing `@string`/`@preamble` blocks | Preserve verbatim, don't touch |
| Single hyphen in page ranges | Always use `--` (double hyphen) for BibTeX page ranges |
| Partially applying title changes | When CrossRef title differs (e.g. preprint→published), replace the ENTIRE title with the CrossRef value — do not edit substrings |
| Ignoring `number` field mismatches | `compare.py` reports `number` mismatches — apply them |

## Preserve

- Entry order, all unchanged fields, empty lines between entries
- User comments (`%` lines not starting with `% bibtidy:`)
- `@string`, `@preamble`, `@comment` blocks
- LaTeX macros and brace-protected capitalization in titles
- If rate-limited, note and continue with next entry
