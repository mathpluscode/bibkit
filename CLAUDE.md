# bibtidy

A Claude Code plugin that validates and fixes BibTeX files.

## Project structure

```
bibtidy/
├── .claude-plugin/
│   └── marketplace.json        ← marketplace catalog
├── plugins/
│   └── bibtidy/
│       ├── .claude-plugin/
│       │   └── plugin.json     ← plugin manifest
│       └── skills/
│           └── bibtidy/
│               └── SKILL.md    ← the skill
├── CLAUDE.md
├── LICENSE
└── README.md
```

## How it works

The skill is invoked via `/bibtidy refs.bib`. Claude reads the .bib file, verifies each entry against Google Scholar and CrossRef (using WebSearch/WebFetch if available, falling back to `curl` via Bash), fixes errors using targeted Edit tool replacements, and adds source URL comments.
