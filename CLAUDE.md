# bibtools

A bibliography toolkit for LaTeX — Claude Code plugin.

## Project structure

```
bibtools/
├── .claude-plugin/
│   ├── marketplace.json        ← marketplace catalog
│   └── plugin.json             ← plugin manifest
├── skills/
│   └── bibtidy/
│       ├── SKILL.md            ← main skill
│       └── tools/
│           ├── compare.py      ← field-level comparison
│           ├── crossref.py     ← CrossRef API client
│           ├── duplicates.py   ← duplicate detector
│           └── fmt.py          ← output format validator
├── tests/
│   ├── conftest.py             ← pytest path setup
│   ├── test_version.py         ← version sync check
│   ├── run_bibtidy_tests.sh    ← end-to-end test runner
│   └── bibtidy/
│       ├── fixtures/
│       │   ├── input.bib       ← test input
│       │   └── expected.bib    ← expected output
│       ├── validate.py         ← structural validation
│       ├── test_compare.py     ← unit tests for compare.py
│       ├── test_crossref.py    ← unit tests for crossref.py
│       ├── test_duplicates.py  ← unit tests for duplicates.py
│       ├── test_fmt.py         ← unit tests for fmt.py
│       └── test_validate.py    ← unit tests for validate.py
├── pyproject.toml              ← project config and pytest settings
├── CLAUDE.md
├── LICENSE
└── README.md
```

## How it works

### bibtidy

Invoke with `/bibtidy refs.bib`. Claude reads the .bib file, dispatches parallel subagents to verify entries against Google Scholar (WebSearch) and CrossRef (bundled `crossref.py`), then applies fixes sequentially using targeted Edit tool replacements. Every change includes the original entry commented out and a source URL for verification.

## Versioning

Version is tracked in three files (`.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `pyproject.toml`). Update all three, then run `uv lock` to sync `uv.lock`.

## Development

The skill's tools are resolved at runtime from `~/.claude/skills/bibtidy/tools`. To test local changes:

- Run `./tests/run_bibtidy_tests.sh` — this syncs local tools to `~/.claude/skills/bibtidy/` before invoking Claude
- Unit tests only: `uv run pytest tests/`

## Code style

- Keep code and comments plain, direct, and easy to scan. Avoid decorative formatting or cleverness that does not add meaning.
- Add comments only when they clarify intent, constraints, or a non-obvious choice. Skip comments that just restate the next line.
- Prefer small shared helpers and simple structure over repeated logic.
