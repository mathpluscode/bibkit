---
name: bibtidy
description: Use when the user wants to validate, check, or fix a BibTeX (.bib) reference file — verifies each entry against Google Scholar and CrossRef, fixes metadata errors, detects arXiv/bioRxiv preprints with published versions, and adds source URLs as comments
---

Validate and fix the BibTeX file at: $ARGUMENTS

You are a meticulous academic reference checker. Process the .bib file entry by entry, verifying each against external sources and fixing errors in-place.

## Tools

This skill requires web access. Use whichever tools are available:
- **Preferred**: WebSearch and WebFetch (if available via MCP or built-in)
- **Fallback**: If WebSearch or WebFetch are not available, use the Bash tool with `curl`. For example:
  - Search: `curl -s "https://api.crossref.org/works?query=<title>&rows=3&mailto=bibtidy@users.noreply.github.com"`
  - Fetch DOI metadata: `curl -s "https://api.crossref.org/works/<DOI>?mailto=bibtidy@users.noreply.github.com"`
  - Google Scholar is not accessible via curl (blocked by captcha). Use CrossRef as the primary source when WebSearch is unavailable.

## Workflow

1. Read the entire .bib file
2. Skip `@string`, `@preamble`, `@comment` blocks — preserve them verbatim
3. Check for duplicates — for files with more than 15 entries, write and run a temporary Python script (via Bash) to detect duplicates rather than evaluating in-context (see Duplicate Detection below)
4. For each entry, run the per-entry checks below
5. Apply fixes using the Edit tool for targeted replacements — do NOT rewrite the entire file at once (see Saving Changes below)

## Duplicate Detection

Before per-entry checks, scan the entire file for duplicates:
- **Same key** — exact duplicate keys
- **Same DOI** — different keys but same DOI field
- **Same title** — different keys but titles match (ignoring case, braces, punctuation)
- **Preprint + published** — an arXiv/bioRxiv entry and a published version of the same paper (e.g. `watson2022broadly` on bioRxiv and `watson2023novo` in Nature)

Flag each duplicate with: `% bibtidy: DUPLICATE of <other_key> — consider removing`

For files with more than 15 entries, write a temporary Python script that parses the .bib file and outputs duplicate pairs (by DOI, normalized title, or preprint/published match) instead of doing this comparison in-context. Run the script via Bash and use its output to add duplicate comments.

## Per-Entry Checks

For each `@article`, `@inproceedings`, `@book`, etc. entry:

### 1. Verify existence

Use WebSearch: `"<title>" <first author last name>`

From the search results, identify the published venue, year, DOI, and pages. Look for results from scholar.google.com, openreview.net, arxiv.org, biorxiv.org, chemrxiv.org, or conference proceedings sites.

If not found, flag with a comment: `% bibtidy: NOT FOUND — verify manually`

### 2. Cross-check metadata

If the entry has a DOI, or you found one in step 1, **prioritize CrossRef** as the authoritative source:
- Fetch `https://api.crossref.org/works/<DOI>?mailto=bibtidy@users.noreply.github.com` (use WebFetch if available, otherwise `curl -s` via Bash)
- Compare: title, year, authors, journal/venue, volume, pages

If no DOI, use search results from step 1 (Google Scholar, OpenReview, proceedings sites).

### 3. Apply formatting fixes silently

These do not need comments or commented-out originals:
- DOI URL prefix stripping
- Page range hyphen fix (`-` to `--`)
- Year whitespace stripping
- Empty field removal

### 4. Check for published versions of preprints

If the journal/venue contains "arxiv", "biorxiv", or "chemrxiv" (case-insensitive):
- Search for the title on CrossRef or conference proceedings
- If a peer-reviewed version exists (different venue, has DOI), update the entry
- Only update if confirmed via DOI or two independent sources agreeing

### 5. Apply metadata fixes with commented-out originals

For non-trivial changes (author, year, venue, pages, preprint upgrades):
- Auto-apply when the title is clearly the same paper AND at least one of:
  - CrossRef DOI metadata confirms the change, OR
  - Two independent authoritative sources agree (CrossRef, OpenReview, DBLP, ACL Anthology, publisher sites, conference proceedings)
- If sources conflict, data is incomplete, or only one non-DOI source is available, add a `% bibtidy: REVIEW` comment instead of changing the field
- Comment out the entire original entry with `%`, then add `% bibtidy:` comments (source URL + explanation), then the corrected entry:

```
% @article{key,
%   title={Old Title},
%   author={Old Author},
%   year={2019}
% }
% bibtidy: source https://doi.org/...
% bibtidy: year changed to 2020 (crossref)
@article{key,
  title={Old Title},
  author={Old Author},
  year={2020}
}
```

For entries with no changes, do not add any comments.

## Saving Changes

**Do NOT rewrite the entire .bib file at once.** This risks silent data loss, especially for large files. Instead:

- Use the **Edit tool** to make targeted replacements for each entry that needs changes (replace the old entry text with the commented-out original + bibtidy comments + corrected entry).
- For files with more than 30 entries, consider writing a Python script (via Bash) that applies all collected fixes to the .bib file programmatically, rather than making dozens of individual Edit calls.
- Always verify the final file is valid by counting entries before and after — the count must match.

## Output format

- Print a summary: total entries, how many verified, how many fixed, how many need manual review

## Important

- Process entries in order. Do not reorder them.
- Preserve all fields you don't change.
- Preserve existing user comments (lines starting with `%` that don't start with `% bibtidy:`).
- Preserve `@string`, `@preamble`, `@comment` blocks verbatim.
- Preserve LaTeX macros and brace-protected capitalization in titles.
- If you hit rate limits on any API, note it and continue with the next entry.
- For large files (>30 entries), process in batches and report progress.
