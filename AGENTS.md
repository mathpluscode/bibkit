# bibtools

A bibliography toolkit for LaTeX, built as agent skills. Explore the repo to understand the project structure before making changes.

## General principles

Bias toward action. Do not spend excessive time exploring files or asking clarifying questions when the task is clear. Start implementing and iterate.

## Code changes

- When fixing bugs or implementing changes, do NOT fix things that aren't actually broken. If you're unsure whether something is a real bug, ask before implementing a fix. Never apply fixes for theoretical issues that can't occur in practice given the actual workflow.
- When making changes, always check README.md and other documentation files for references that need updating. Check for hardcoded magic numbers that should use existing config values.

## Code review

When asked to do a code review, only flag real actionable issues. Do NOT over-engineer fixes or apply unnecessary changes. When in doubt, propose the fix and wait for user approval before implementing.

## How it works

### bibtidy

In Claude Code, invoke with `/bibtidy refs.bib`. In Codex, ask it to use the `bibtidy` skill on a `.bib` file. The agent reads the file, dispatches parallel subagents to verify entries against Google Scholar and CrossRef (bundled `crossref.py`), then applies fixes sequentially with targeted edits. Every change includes the original entry commented out and one or more source URLs for verification.

## Versioning

Version is tracked in three files (`.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `pyproject.toml`). Update all three, then run `uv lock` to sync `uv.lock`.

## Development

The skill's tools live under `skills/bibtidy/tools/` in this repo. At runtime, determine which agent platform you are (Claude Code, Codex, etc.) and resolve the installed tools directory accordingly (e.g. `~/.claude/skills/bibtidy/tools` for Claude Code, `~/.codex/skills/bibtidy/tools` for Codex). To test local changes:

- Run `./tests/run_bibtidy_cc_tests.sh` — this syncs local tools to `~/.claude/skills/bibtidy/` before invoking Claude
- Run `./tests/run_bibtidy_codex_tests.sh` for the Codex end-to-end path
- Unit tests only: `uv run pytest tests/`

## Code style

- Keep code and comments plain, direct, and easy to scan. Avoid decorative formatting or cleverness that does not add meaning.
- Add comments only when they clarify intent, constraints, or a non-obvious choice. Skip comments that just restate the next line.
- Prefer small shared helpers and simple structure over repeated logic.
