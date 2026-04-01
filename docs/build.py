"""Generate docs/index.html from test fixtures.

Reads tests/bibtidy/fixtures/{input,expected}.bib, computes per-entry diffs,
and writes a self-contained HTML page with GitHub-style diff rendering.

Usage:
    python docs/build.py
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_BIB = ROOT / "tests" / "bibtidy" / "fixtures" / "input.bib"
EXPECTED_BIB = ROOT / "tests" / "bibtidy" / "fixtures" / "expected.bib"
OUTPUT_HTML = ROOT / "docs" / "index.html"


# ---------------------------------------------------------------------------
# BibTeX parsing
# ---------------------------------------------------------------------------

def parse_entries(text: str) -> list[dict]:
    """Parse a .bib file into a list of entry dicts.

    Each dict has:
        key: citation key (e.g. "vaswani2017attention")
        lines: list of raw lines for the entry body
        bibtidy_comments: list of "% bibtidy: ..." lines preceding the entry
        is_duplicate_target: True if this entry only gained a DUPLICATE comment
    """
    entries: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip @string, @preamble, blank lines, and descriptive comments
        if (
            not line.strip()
            or line.strip().startswith("% ---")
            or line.strip().startswith("% Test fixture")
            or line.strip().startswith("% Each entry")
            or re.match(r"^@(string|preamble)", line.strip(), re.IGNORECASE)
        ):
            i += 1
            continue

        # Collect commented-out original and bibtidy comments
        bibtidy_comments: list[str] = []
        # Skip commented-out original entry lines (% @... or %   ...)
        while i < len(lines) and lines[i].startswith("%"):
            stripped = lines[i].lstrip("% ").strip()
            if lines[i].strip().startswith("% bibtidy:"):
                bibtidy_comments.append(lines[i].strip())
            i += 1

        # Now we should be at the @type{key, line
        if i >= len(lines):
            break
        line = lines[i]
        m = re.match(r"@\w+\{(\S+),", line)
        if not m:
            i += 1
            continue

        key = m.group(1).rstrip(",")
        entry_lines = [line]
        i += 1
        # Collect until closing brace
        brace_depth = line.count("{") - line.count("}")
        while i < len(lines) and brace_depth > 0:
            entry_lines.append(lines[i])
            brace_depth += lines[i].count("{") - lines[i].count("}")
            i += 1

        entries.append({
            "key": key,
            "lines": entry_lines,
            "bibtidy_comments": bibtidy_comments,
        })

    return entries


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def compute_diff(input_lines: list[str], expected_lines: list[str]) -> list[tuple[str, str]]:
    """Return list of (type, line) where type is 'ctx', 'del', or 'add'."""
    result = []
    sm = difflib.SequenceMatcher(None, input_lines, expected_lines)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for line in input_lines[i1:i2]:
                result.append(("ctx", line))
        elif op == "replace":
            for line in input_lines[i1:i2]:
                result.append(("del", line))
            for line in expected_lines[j1:j2]:
                result.append(("add", line))
        elif op == "delete":
            for line in input_lines[i1:i2]:
                result.append(("del", line))
        elif op == "insert":
            for line in expected_lines[j1:j2]:
                result.append(("add", line))
    return result


# ---------------------------------------------------------------------------
# Badge classification
# ---------------------------------------------------------------------------

def classify_entry(bibtidy_comments: list[str], diff: list[tuple[str, str]]) -> tuple[str, str]:
    """Return (badge_class, badge_label) based on bibtidy comments."""
    joined = " ".join(bibtidy_comments).lower()
    has_changes = any(t != "ctx" for t, _ in diff)

    if not has_changes and not bibtidy_comments:
        return "badge-ok", "unchanged"
    if "duplicate" in joined:
        return "badge-duplicate", "duplicate detected"
    if "removed" in joined and ("author" in joined or "editor" in joined or "co-author" in joined):
        return "badge-fix", "author fix"
    if "doi" in joined and ("stripped" in joined or "prefix" in joined or "hyphen" in joined):
        return "badge-fix", "formatting fix"
    if "page" in joined and "corrected" in joined:
        return "badge-fix", "page fix"
    if "casing" in joined or "surname" in joined:
        return "badge-fix", "metadata fix"
    if "published" in joined or "updated from arxiv" in joined:
        return "badge-upgrade", "preprint &#8594; published"
    if has_changes:
        return "badge-fix", "fix"
    return "badge-ok", "unchanged"


def make_title(bibtidy_comments: list[str], diff: list[tuple[str, str]]) -> str:
    """Generate a human-readable title for the diff card."""
    joined = " ".join(bibtidy_comments).lower()
    has_changes = any(t != "ctx" for t, _ in diff)

    if not has_changes and not bibtidy_comments:
        return "Correct entry left unchanged"
    if "duplicate" in joined:
        return "bioRxiv preprint duplicated with published version"
    if "updated from arxiv" in joined and "title updated" in joined:
        return "arXiv preprint upgraded with title change"
    if "published" in joined and ("arxiv" in joined or "iclr" in joined):
        return "arXiv preprint upgraded to published version"
    if "removed" in joined and ("editor" in joined or "co-author" in joined):
        return "Editor listed as co-author"
    if "page" in joined and "corrected" in joined:
        return "Wrong page numbers from Google Scholar"
    if "doi" in joined or "hyphen" in joined:
        return "DOI URL prefix and wrong page range hyphen"
    if "casing" in joined or "surname" in joined:
        return "Journal casing and compound surname fix"
    return "Entry corrected"


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"(https?://[^\s,;)\"'&{}]+)")


def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def linkify(s: str) -> str:
    """Escape HTML and convert URLs to clickable links."""
    escaped = escape_html(s)
    return _URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline">\1</a>', escaped)


def render_diff_card(
    title: str,
    badge_class: str,
    badge_label: str,
    bibtidy_comments: list[str],
    diff: list[tuple[str, str]],
) -> str:
    add_count = sum(1 for t, _ in diff if t == "add") + len(bibtidy_comments)
    del_count = sum(1 for t, _ in diff if t == "del")

    parts = []
    parts.append('<div class="diff-card">')
    parts.append('  <div class="diff-header">')
    parts.append(f'    <span class="diff-title">{title}</span>')
    if add_count or del_count:
        stats = ""
        if add_count:
            stats += f'<span class="add-count">+{add_count}</span>'
        if del_count:
            if stats:
                stats += " "
            stats += f'<span class="del-count">-{del_count}</span>'
        parts.append(f'    <span class="stats">{stats}</span>')
    parts.append(f'    <span class="diff-badge {badge_class}">{badge_label}</span>')
    parts.append("  </div>")
    parts.append('  <div class="diff-body">')
    # bibtidy comments as added lines
    for comment in bibtidy_comments:
        parts.append(f'    <div class="diff-line add">+{linkify(comment)}</div>')
    # diff lines
    for typ, line in diff:
        prefix = {"ctx": " ", "del": "-", "add": "+"}[typ]
        parts.append(f'    <div class="diff-line {typ}">{prefix}{linkify(line)}</div>')
    parts.append("  </div>")
    parts.append("</div>")
    return "\n".join(parts)


def build_html(cards_html: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>bibtools</title>
<style>
  :root {{
    --bg: #ffffff;
    --surface: #f6f8fa;
    --border: #d0d7de;
    --text: #1f2328;
    --text-muted: #656d76;
    --del-bg: #ffebe9;
    --del-line: #cf222e;
    --add-bg: #dafbe1;
    --add-line: #116329;
    --hunk-bg: #ddf4ff;
    --hunk-text: #0969da;
    --accent: #0969da;
    --badge-fix-bg: #dafbe1;
    --badge-fix-text: #116329;
    --badge-fix-border: #aceebb;
    --badge-upgrade-bg: #ddf4ff;
    --badge-upgrade-text: #0969da;
    --badge-upgrade-border: #80ccff;
    --badge-dup-bg: #fff8c5;
    --badge-dup-text: #9a6700;
    --badge-dup-border: #d4a72c;
    --badge-ok-bg: #f6f8fa;
    --badge-ok-text: #656d76;
    --badge-ok-border: #d0d7de;
    --tab-active: #0969da;
    --tab-hover: #f6f8fa;
  }}

  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117;
      --surface: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --text-muted: #8b949e;
      --del-bg: #3d1f28;
      --del-line: #ff7b72;
      --add-bg: #1a3326;
      --add-line: #7ee787;
      --hunk-bg: #1c2536;
      --hunk-text: #79c0ff;
      --accent: #58a6ff;
      --badge-fix-bg: #2ea04333;
      --badge-fix-text: #7ee787;
      --badge-fix-border: #2ea04366;
      --badge-upgrade-bg: #1f6feb33;
      --badge-upgrade-text: #58a6ff;
      --badge-upgrade-border: #1f6feb66;
      --badge-dup-bg: #d2992233;
      --badge-dup-text: #e3b341;
      --badge-dup-border: #d2992266;
      --badge-ok-bg: #30363d;
      --badge-ok-text: #8b949e;
      --badge-ok-border: #30363d;
      --tab-active: #58a6ff;
      --tab-hover: #161b22;
    }}
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }}

  .header {{
    border-bottom: 1px solid var(--border);
    padding: 2rem 0;
    text-align: center;
  }}

  .header h1 {{ font-size: 2rem; font-weight: 600; margin-bottom: 0.5rem; }}
  .header p {{ color: var(--text-muted); font-size: 1.1rem; }}

  .container {{ max-width: 960px; margin: 0 auto; padding: 0 1rem 2rem; }}

  .tabs {{
    display: flex;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2rem;
  }}

  .tab {{
    padding: 0.75rem 1.25rem;
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-muted);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    background: none;
    border-top: none;
    border-left: none;
    border-right: none;
    font-family: inherit;
  }}

  .tab:hover {{ color: var(--text); background: var(--tab-hover); }}
  .tab.active {{ color: var(--tab-active); border-bottom-color: var(--tab-active); }}

  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  .section-title {{
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
  }}

  .section {{ margin-bottom: 2.5rem; }}

  .demo img {{ max-width: 100%; border-radius: 6px; border: 1px solid var(--border); }}

  .install-step {{ margin-bottom: 1rem; }}
  .install-step p {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.4rem; }}

  .code-block {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  .code-block code {{ flex: 1; user-select: all; }}

  .copy-btn {{
    background: none;
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text-muted);
    cursor: pointer;
    padding: 0.2rem 0.4rem;
    font-size: 0.75rem;
    font-family: inherit;
    margin-left: 0.75rem;
    flex-shrink: 0;
  }}

  .copy-btn:hover {{ color: var(--text); border-color: var(--text-muted); }}

  .diff-card {{
    border: 1px solid var(--border);
    border-radius: 6px;
    margin-bottom: 2rem;
    overflow: hidden;
  }}

  .diff-header {{
    background: var(--surface);
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}

  .diff-title {{ font-weight: 600; font-size: 0.9rem; }}

  .diff-badge {{
    font-size: 0.75rem;
    padding: 0.1rem 0.5rem;
    border-radius: 2em;
    font-weight: 500;
    margin-left: auto;
  }}

  .badge-fix {{ background: var(--badge-fix-bg); color: var(--badge-fix-text); border: 1px solid var(--badge-fix-border); }}
  .badge-upgrade {{ background: var(--badge-upgrade-bg); color: var(--badge-upgrade-text); border: 1px solid var(--badge-upgrade-border); }}
  .badge-duplicate {{ background: var(--badge-dup-bg); color: var(--badge-dup-text); border: 1px solid var(--badge-dup-border); }}
  .badge-ok {{ background: var(--badge-ok-bg); color: var(--badge-ok-text); border: 1px solid var(--badge-ok-border); }}

  .diff-body {{
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.8rem;
    line-height: 1.7;
    overflow-x: auto;
  }}

  .diff-hunk {{
    background: var(--hunk-bg);
    color: var(--hunk-text);
    padding: 0.25rem 1rem;
    font-size: 0.75rem;
  }}

  .diff-line {{ padding: 0 1rem; white-space: pre; }}
  .diff-line.del {{ background: var(--del-bg); color: var(--del-line); }}
  .diff-line.add {{ background: var(--add-bg); color: var(--add-line); }}
  .diff-line.ctx {{ color: var(--text-muted); }}

  .stats {{ font-size: 0.8rem; color: var(--text-muted); margin-left: 0.5rem; }}
  .stats .add-count {{ color: var(--add-line); }}
  .stats .del-count {{ color: var(--del-line); }}

  .diff-body a {{ color: var(--accent); }}
</style>
</head>
<body>

<div class="header">
  <div class="container">
    <h1>bibtools</h1>
    <p>A bibliography toolkit for LaTeX &mdash; built as a Claude Code plugin.</p>
  </div>
</div>

<div class="container">

<div class="tabs">
  <button class="tab active" onclick="switchTab('bibtidy')">bibtidy</button>
</div>

<div id="tab-bibtidy" class="tab-content active">

<p style="color: var(--text-muted); margin-bottom: 1.5rem;">bibtidy cross-checks BibTeX entries against Google Scholar, CrossRef, and conference/journal sites. It upgrades arXiv/bioRxiv preprints to published versions (even when the title changed upon publication), corrects metadata (authors, pages, venues), and flags semantic duplicates.</p>

<div class="section">
  <div class="demo">
    <img src="bibtidy_demo.gif" alt="bibtidy demo">
  </div>
</div>

<div class="section">
  <h2 class="section-title">Install</h2>

  <div class="install-step">
    <p>Add the marketplace in Claude Code:</p>
    <div class="code-block"><code>/plugin marketplace add mathpluscode/bibtools</code><button class="copy-btn" onclick="copyCode(this)">Copy</button></div>
  </div>

  <div class="install-step">
    <p>Install the plugin:</p>
    <div class="code-block"><code>/plugin install bibtools@mathpluscode-bibtools</code><button class="copy-btn" onclick="copyCode(this)">Copy</button></div>
  </div>

  <div class="install-step">
    <p>Reload plugins:</p>
    <div class="code-block"><code>/reload-plugins</code><button class="copy-btn" onclick="copyCode(this)">Copy</button></div>
  </div>

</div>

<div class="section">
  <h2 class="section-title">Examples</h2>

{cards_html}

</div>

</div>

</div>

<script>
function copyCode(btn) {{
  const code = btn.previousElementSibling.textContent;
  navigator.clipboard.writeText(code).then(() => {{
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  }});
}}

function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector(`[onclick="switchTab('${{name}}')"]`).classList.add('active');
  document.getElementById(`tab-${{name}}`).classList.add('active');
}}
</script>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    input_text = INPUT_BIB.read_text()
    expected_text = EXPECTED_BIB.read_text()

    input_entries = {e["key"]: e for e in parse_entries(input_text)}
    expected_entries = parse_entries(expected_text)

    # Build a lookup for expected entries
    expected_by_key = {}
    for e in expected_entries:
        expected_by_key[e["key"]] = e

    # Generate diff cards, separating unchanged entries
    changed_cards = []
    unchanged_cards = []

    # Process in expected order to preserve fixture ordering
    seen_keys: set[str] = set()
    for exp in expected_entries:
        key = exp["key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)

        inp = input_entries.get(key)
        if not inp:
            continue

        diff = compute_diff(inp["lines"], exp["lines"])
        bibtidy_comments = exp["bibtidy_comments"]
        badge_class, badge_label = classify_entry(bibtidy_comments, diff)
        title = make_title(bibtidy_comments, diff)
        # Handle duplicate pair: include second entry in same card
        if "duplicate" in " ".join(bibtidy_comments).lower():
            # Find the target of the duplicate
            m = re.search(r"DUPLICATE of (\S+)", " ".join(bibtidy_comments))
            if m:
                target_key = m.group(1)
                target = expected_by_key.get(target_key)
                if target and target_key in input_entries:
                    # Append blank line + second entry to both sides
                    inp_combined = inp["lines"] + [""] + input_entries[target_key]["lines"]
                    exp_combined = exp["lines"] + [""] + target["lines"]
                    diff = compute_diff(inp_combined, exp_combined)
                    seen_keys.add(target_key)

        card = render_diff_card(title, badge_class, badge_label, bibtidy_comments, diff)

        if badge_class == "badge-ok":
            unchanged_cards.append(card)
        else:
            changed_cards.append(card)

    # Unchanged at the bottom
    all_cards = changed_cards + unchanged_cards
    cards_html = "\n\n".join(all_cards)

    html = build_html(cards_html)
    OUTPUT_HTML.write_text(html)


if __name__ == "__main__":
    main()
