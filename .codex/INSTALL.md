# Installing bibtools for Codex

Enable the `bibtidy` skill in Codex via native skill discovery.

## Prerequisites

- Git

## Installation

1. Clone the repository:

```bash
git clone https://github.com/mathpluscode/bibtools.git ~/.codex/bibtools
```

2. Create the Codex skills symlink:

```bash
mkdir -p ~/.codex/skills
ln -s ~/.codex/bibtools/skills/bibtidy ~/.codex/skills/bibtidy
```

3. Restart Codex so it discovers the new skill.

## Verify

```bash
ls -la ~/.codex/skills/bibtidy
```

You should see a symlink pointing at `~/.codex/bibtools/skills/bibtidy`.

## Updating

```bash
cd ~/.codex/bibtools && git pull
```

The skill updates immediately through the symlink. Restart Codex if it is already running.
