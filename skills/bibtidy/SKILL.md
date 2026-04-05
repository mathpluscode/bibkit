---
name: bibtidy
description: Use when the user wants to validate, check, or fix a BibTeX (.bib) reference file — wrong authors, stale arXiv preprints, incorrect metadata, duplicate entries, formatting issues
metadata:
  short-description: Validate and fix BibTeX reference files
allowed-tools: Bash(python3 *), Bash(cp *), Bash(rm *), Read, Agent, WebSearch
---

Use this skill whenever the user wants to validate, check, clean up, or fix a BibTeX `.bib` file.

If the user request or skill invocation includes an explicit `.bib` path, operate on that file.

If the file path is missing or does not exist, ask for the path.

Usage examples:
- Claude Code slash command: `/bibtidy <path-to-file.bib>`
- Codex request: `Use the bibtidy skill to validate and fix <path-to-file.bib>`

You are a meticulous academic reference checker. Process the .bib file entry by entry, verifying each against external sources and fixing errors in-place.

Assume standard brace-style BibTeX entries like `@article{...}`. Parenthesized BibTeX blocks like `@article(...)` are not supported. If you see them, stop and tell the user to convert them to brace style first.

## Quick Reference

| Tool | Command |
|------|---------|
| **Field comparison** | `python3 $TOOLS_DIR/compare.py <file.bib> [--key KEY]` |
| CrossRef DOI lookup | `python3 $TOOLS_DIR/crossref.py doi <DOI>` |
| CrossRef title search | `python3 $TOOLS_DIR/crossref.py search "<title>"` |
| CrossRef bibliographic search | `python3 $TOOLS_DIR/crossref.py bibliographic "<query>"` |
| Remove exact duplicates | `python3 $TOOLS_DIR/duplicates.py <file.bib> --exact` |
| Detect near-duplicates | `python3 $TOOLS_DIR/duplicates.py <file.bib>` |
| **Apply edits** | `python3 $TOOLS_DIR/edit.py <file.bib> <patches.json>` |
| Web verification | web search (preferred) or CrossRef scripts (fallback) |

## Script Path Resolution

All bundled tools live in the `tools/` directory next to this SKILL.md. Before running any tool, resolve the absolute path once:

```
TOOLS_SEARCH_PATH=(
  "${CODEX_HOME:-$HOME/.codex}/skills/bibtidy/tools"
  "$HOME/.claude/skills/bibtidy/tools"
  "${CLAUDE_PLUGIN_ROOT:-/dev/null}/skills/bibtidy/tools"
)
for d in "${TOOLS_SEARCH_PATH[@]}"; do
  if [ -f "$d/crossref.py" ]; then TOOLS_DIR="$d"; break; fi
done
```

Use `$TOOLS_DIR` in every invocation.

## Output Format for Changed Entries

For `fix` patches, each targeted edit MUST contain the original entry, one or more source URLs, an explanation, and the corrected entry. Include URLs for all sources used (CrossRef, DOI, venue page), each on its own `% bibtidy:` line.

```
% @<type>{<key>,
%   <original field 1>,
%   <original field 2>,
%   ...
% }
% bibtidy: <URL>
% bibtidy: <what changed>
@<type>{<key>,
  <corrected field 1>,
  <corrected field 2>,
  ...
}
```

- **Part 1** — entire original entry, every line prefixed by `% `. All lines, not just the first.
- **Part 2** — `% bibtidy: ` followed by a URL. Must be exactly `% bibtidy: https://...`.
- **Part 3** — `% bibtidy: ` followed by explanation of what changed.
- **Part 4** — corrected entry.

Exceptions:
- `not_found` entries get the `% bibtidy: NOT FOUND ...` line plus the fully commented-out original entry. Do NOT add a URL line.
- `duplicate` entries get `% bibtidy: DUPLICATE of <other_key> — consider removing` above the original entry. Do NOT add URL or explanation lines unless the tool behavior changes.

For unchanged entries, do NOT add any comments or URLs.

## Workflow

1. Read the .bib file, note the file path
2. Back up for format validation: `cp <file>.bib <file>.bib.orig`
3. Preserve `@string`, `@preamble`, `@comment` blocks verbatim
4. **Remove exact duplicates**: `python3 $TOOLS_DIR/duplicates.py <file.bib> --exact` — this comments out entries that are identical (same key, same type, same fields). Safe to auto-remove since no information is lost.
5. **Run field comparison**: `python3 $TOOLS_DIR/compare.py <file.bib>` — this programmatically compares every entry against CrossRef and returns exact field-level mismatches. Do NOT skip this step or rely on visual comparison alone. The output is a JSON list; each element has `key`, `versions` (a list of alternative CrossRef candidate matches for the same entry, each with `mismatches`, `url`, `doi`, etc.), and `error`. When multiple versions are returned, choose the best matching candidate; do not combine fields from different versions. **Skip rule**: if an entry has zero mismatches across all versions and no error in the compare.py output, skip it entirely — do NOT investigate, modify, or add comments to it. Only proceed with entries that compare.py flagged (mismatches or errors).
6. **Verify every planned modification with web search** — for entries that compare.py flagged with mismatches or errors, verify the planned action via web search. For `fix` patches, gather one or more source URLs. Entries where `compare.py` returned an error (e.g. "No exact title match") still need full verification — the verification agent should search for the paper and check all fields. **Important: after selecting the best-matching version, verification agents MUST NOT override that selected version's `compare.py` field values.** CrossRef is the authoritative source for metadata (pages, volume, number, etc.) because it receives data directly from publishers via DOI registration. When web search finds a conflicting value (e.g. different page numbers on a conference website), always use the CrossRef value and add `% bibtidy: REVIEW` if desired — but do NOT keep the old value.
7. **Flag hallucinated/non-existent references** — if compare.py returned an error (e.g. "No CrossRef results found" or "No exact title match in CrossRef results") AND web search also finds no matching paper, the reference likely does not exist. Add `% bibtidy: NOT FOUND — no matching paper on CrossRef or web search; verify this reference exists` above the entry, then comment out the entire entry (prefix every line with `% `). Do NOT add a URL line.
8. Apply fixes **sequentially** using `edit.py` — do NOT edit the .bib file directly with agent editing tools (for example, Claude Code Edit or Codex `apply_patch`), and do NOT rewrite the entire file. Build a patches.json for each entry (or batch) and run `python3 $TOOLS_DIR/edit.py <file.bib> <patches.json>`. This ensures the commented original, source URLs, and explanation are always included. After selecting the correct version, you MUST apply **every** mismatch from that selected version — do not skip any field (including `author`, `number`, `pages`, `volume`). In particular, if the bib entry uses `and others` but CrossRef returns the full author list, you MUST replace the truncated list with the complete one from CrossRef. Use the `crossref_value` exactly as given (do NOT rephrase, reformat, or partially apply it). For title mismatches on preprint→published upgrades, replace the entire title with the CrossRef title — do NOT try to edit parts of the old title. Never reject a CrossRef value because another source disagrees. Every patch MUST include `urls` (list of source URLs) and `explanation` (what changed and why). Include the CrossRef URL from compare.py's `url` field when available, plus any other authoritative source (DOI URL, venue page) found via web search.
9. **Post-fix exact duplicate removal**: `python3 $TOOLS_DIR/duplicates.py <file.bib> --exact` — entries that were different before fixing may now be identical after metadata corrections. Comment out any new exact duplicates.
10. **Detect near-duplicates**: `python3 $TOOLS_DIR/duplicates.py <file.bib>` — flag entries that share the same key, DOI, or title (with a shared author), plus likely preprint→published pairs with the same lead author and overlapping significant title words, but are not identical. Apply `duplicate` patches via `edit.py` to add `% bibtidy: DUPLICATE of <other_key>` comments. Do NOT delete or comment out near-duplicates.
11. Run format validation; fix violations and re-run until clean
12. Delete backup: `rm <file>.bib.orig`
13. Print a Markdown summary table with headers `Metric | Count` and exactly these rows: total entries, verified, fixed, not found, exact duplicates removed, near-duplicates flagged. Do NOT include a separate "needs manual review" row.

## Parallel Verification with Subagents

Use subagents, when available, to verify multiple entries concurrently. This dramatically reduces wall-clock time (e.g., 7 entries: ~1 min parallel vs ~5 min sequential; 100 entries: ~3 min vs ~40 min). If subagents are unavailable, do the same verification work sequentially yourself.

**Step 1 — Dispatch verification agents:** For entries that `compare.py` flagged with mismatches or errors, launch a subagent that:
- For mismatches: uses web search to confirm the CrossRef data (especially for preprint upgrades and author changes)
- For errors (e.g. paper not found in CrossRef): uses web search to verify **every** field from scratch — title, author, journal/booktitle, volume, number, pages, year. Do NOT skip number or other fields just because they look plausible.
- Returns a JSON summary: key, whether each mismatch is confirmed, source URL, CrossRef URL (if there is a CrossRef match), any additional corrections found

**When CrossRef fails**, find the paper's official venue page via web search. Many venues (JMLR, NeurIPS, CVPR, etc.) provide a downloadable `.bib` file — fetch it directly when possible. An official `.bib` is the most reliable source: it has exact title, authors, volume, number, and pages with no guessing.

Launch verification subagents in one batch so they run concurrently. Cap at **6 subagents** and distribute entries evenly across them (e.g., 18 entries = 3 per subagent, 60 entries = 10 per subagent). For ≤6 entries, use one subagent per entry. If the user explicitly requests more parallelism, you may increase beyond 6.

**Step 2 — Collect results:** Read each agent's returned summary.

**Step 3 — Apply edits sequentially using `edit.py`:** Using the lookup results, build a patches.json and run `python3 $TOOLS_DIR/edit.py <file.bib> <patches.json>` one entry at a time. Do NOT edit the .bib file directly with agent editing tools such as Claude Code Edit or Codex `apply_patch`. Edits MUST be sequential (parallel edits to the same file cause conflicts).

**Example agent prompt:**
```
Verify this BibTeX entry against CrossRef. Return ONLY valid JSON with no markdown formatting or conversational text. Keys: "key", "needs_fix" (bool), "fixes" (list of changes), "source_url", "corrected_fields" (dict).

TOOLS_SEARCH_PATH=(
  "${CODEX_HOME:-$HOME/.codex}/skills/bibtidy/tools"
  "$HOME/.claude/skills/bibtidy/tools"
  "${CLAUDE_PLUGIN_ROOT:-/dev/null}/skills/bibtidy/tools"
)
for d in "${TOOLS_SEARCH_PATH[@]}"; do
  if [ -f "$d/crossref.py" ]; then TOOLS_DIR="$d"; break; fi
done

Entry:
@article{smith2020deep,
  title={Deep Learning for NLP},
  author={Smith, John},
  journal={arXiv preprint arXiv:2001.12345},
  year={2020}
}
```

## Duplicate Detection

Duplicate handling has three phases (see workflow steps 4, 9, 10):

**Exact duplicates** (same key, type, and all field values): `python3 $TOOLS_DIR/duplicates.py <file.bib> --exact` comments them out automatically. Run before and after metadata fixes.

**Near-duplicates** (same key, DOI, or title with shared author, plus likely preprint→published pairs with the same lead author and overlapping significant title words, but different content): `python3 $TOOLS_DIR/duplicates.py <file.bib>` returns a JSON array of pairs. For each, apply a `duplicate` patch via `edit.py` to add `% bibtidy: DUPLICATE of <other_key>`. Do NOT delete or comment out near-duplicates.

## Per-Entry Checks

For each `@article`, `@inproceedings`, `@book`, etc.:

**1. Verify existence** — Search for `"<title>" <first author last name>`. If not found: `% bibtidy: NOT FOUND — verify manually`

**2. Cross-check metadata** — `compare.py` runs both `crossref.py search "<title>"` and `crossref.py bibliographic "<title>"` unconditionally, plus `crossref.py doi <DOI>` when a DOI exists, deduplicating results by DOI. Only exact normalized title matches are kept. Compare title, year, authors, journal, volume, number, pages.

**3. Check for published preprints** — If journal contains "arxiv"/"biorxiv"/"chemrxiv", search for published version. Update title, venue, year, volume, pages, entry type. Only update if confirmed via DOI or two independent sources.

**4. Apply fixes** — DOI URL prefix stripping, page hyphen fix (`-` → `--`), year whitespace, empty field removal, author corrections, venue/year/volume/pages corrections, preprint upgrades. Missing `pages` fields are NOT flagged — some venues (e.g. NeurIPS, ICLR) intentionally omit page numbers. Only mismatched pages (both sides have values that differ) are reported. Do not add a `doi` field to an entry that lacks one.

**Always apply the best-available fix.** If confidence is low (sources conflict, data incomplete, or only partial match), still apply the fix but add `% bibtidy: REVIEW — <reason>` explaining why it needs human attention.

## Saving Changes

- Use targeted replacements — not whole-file rewrites
- For large files (>30 entries), process in batches of ~15, reporting progress
- Verify entry count before and after — must match

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Missing `% bibtidy:` URL | Every changed entry needs a URL — use DOI URL or venue page |
| Incomplete commented original | Comment out ALL lines of the original, including closing `}` |
| Adding comments to unchanged entries | Only changed entries get bibtidy comments — if compare.py reports zero mismatches and no error, do not touch the entry |
| Rewriting entire file | Use `edit.py` with one entry or a small batch at a time; never rewrite the `.bib` file directly |
| Deleting duplicate entries | Flag with comment only — never delete |
| Losing `@string`/`@preamble` blocks | Preserve verbatim, don't touch |
| Single hyphen in page ranges | Always use `--` (double hyphen) for BibTeX page ranges |
| Partially applying title changes | When CrossRef title differs (e.g. preprint→published), replace the ENTIRE title with the CrossRef value — do not edit substrings |
| Ignoring `number` field mismatches | `compare.py` reports `number` mismatches — apply them |
| Adding `doi` when entry didn't have one | Never inject a `doi` field into an entry that lacks one |
| Using agent editing tools instead of `edit.py` | Always use `edit.py` to apply changes, never edit the .bib file directly with Claude Code Edit, Codex `apply_patch`, or similar tools. Direct edits skip the commented original, URLs, and explanation |

## Preserve

- Entry order, all unchanged fields, empty lines between entries
- User comments (`%` lines not starting with `% bibtidy:`)
- `@string`, `@preamble`, `@comment` blocks
- LaTeX macros and brace-protected capitalization in titles
- If rate-limited, note and continue with next entry
