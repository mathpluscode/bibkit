#!/usr/bin/env bash
# Run bibtidy on the test fixture through Codex and validate the output.
#
# Usage:
#   ./tests/run_bibtidy_codex_tests.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_DIR/.uv-cache}"
INPUT="$SCRIPT_DIR/bibtidy/fixtures/input.bib"
GOT="$SCRIPT_DIR/bibtidy/fixtures/got_codex.bib"
VALIDATOR="$SCRIPT_DIR/bibtidy/validate.py"
CODEX_HOME_DIR="${BIBTIDY_CODEX_HOME:-${CODEX_HOME:-$HOME/.codex}}"
export CODEX_HOME="$CODEX_HOME_DIR"
SKILL_SRC="$REPO_DIR/skills/bibtidy"
SKILL_DST="$CODEX_HOME_DIR/skills/bibtidy"

echo "=> Running unit tests..."
uv run pytest "$REPO_DIR/tests/" -v || { echo "=> Unit tests failed, aborting."; exit 1; }
echo ""

echo "=> Syncing bibtidy skill for Codex..."
mkdir -p "$CODEX_HOME_DIR/skills"
rm -rf "$SKILL_DST"
cp -r "$SKILL_SRC" "$SKILL_DST"
echo "=> Synced skill to $SKILL_DST"

cp "$INPUT" "$GOT"
ENTRY_COUNT=$(grep '^@' "$GOT" | grep -cv '^@\(string\|preamble\|comment\)')
echo "=> Found $ENTRY_COUNT entries in test fixture"
echo "=> Running bibtidy with Codex..."
echo ""

START_TIME=$SECONDS

codex --search exec \
    --full-auto \
    --add-dir "$CODEX_HOME_DIR/skills" \
    -C "$REPO_DIR" \
    "Use the bibtidy skill to validate and fix $GOT in place. Follow the skill exactly." >/dev/null

ELAPSED=$(( SECONDS - START_TIME ))
echo ""
echo "=> bibtidy complete in ${ELAPSED}s ($ENTRY_COUNT entries)."

echo ""
echo "=> Structural validation..."
echo ""
python3 "$VALIDATOR" "$GOT"
