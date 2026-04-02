#!/usr/bin/env bash
# Run bibtidy on the test fixture and validate the output.
#
# Usage:
#   ./tests/run_bibtidy_cc_tests.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_DIR/.uv-cache}"
INPUT="$SCRIPT_DIR/bibtidy/fixtures/input.bib"
GOT="$SCRIPT_DIR/bibtidy/fixtures/got_cc.bib"
VALIDATOR="$SCRIPT_DIR/bibtidy/validate.py"
SKILL_SRC="$REPO_DIR/skills/bibtidy"
SKILL_DST="$HOME/.claude/skills/bibtidy"
SKILL_BACKUP=""


# Run unit tests first — fail fast before the slower Claude invocation
echo "=> Running unit tests..."
uv run pytest "$REPO_DIR/tests/" -v || { echo "=> Unit tests failed, aborting."; exit 1; }
echo ""

# Back up existing skill if present, restore on exit
if [ -d "$SKILL_DST" ]; then
    SKILL_BACKUP="$(mktemp -d)"
    cp -r "$SKILL_DST" "$SKILL_BACKUP/bibtidy"
    echo "=> Backed up existing skill to $SKILL_BACKUP"
fi
restore_skill() {
    if [ -n "$SKILL_BACKUP" ]; then
        rm -rf "$SKILL_DST"
        mv "$SKILL_BACKUP/bibtidy" "$SKILL_DST"
        rmdir "$SKILL_BACKUP"
        echo "=> Restored original skill"
    fi
}
trap restore_skill EXIT

# Sync skill to installed location so /bibtidy uses the latest version
rm -rf "$SKILL_DST"
mkdir -p "$SKILL_DST"
cp "$SKILL_SRC/SKILL.md" "$SKILL_DST/SKILL.md"
cp -r "$SKILL_SRC/tools" "$SKILL_DST/"
echo "=> Synced skill to $SKILL_DST"

# Copy input to got_cc.bib — bibtidy edits this copy in-place
cp "$INPUT" "$GOT"
ENTRY_COUNT=$(grep '^@' "$GOT" | grep -cv '^@\(string\|preamble\|comment\)')
echo "=> Found $ENTRY_COUNT entries in test fixture"
echo "=> Running bibtidy..."
echo ""

START_TIME=$SECONDS

claude -p "/bibtidy $GOT" \
    --allowedTools "Agent" "Bash(curl *)" "Bash(python3 *)" "Bash(cp *)" "Bash(rm *)" "Read" "Edit" "Write" "Glob" "Grep" "WebSearch" "WebFetch" \
    --verbose 2>&1

ELAPSED=$(( SECONDS - START_TIME ))
echo ""
echo "=> bibtidy complete in ${ELAPSED}s ($ENTRY_COUNT entries)."

echo ""
echo "=> Structural validation..."
echo ""
python3 "$VALIDATOR" "$GOT"
