"""Unit tests for edit.py."""

from parser import comment_out, find_entry_spans

from edit import _build_entry, _compute_field_order, _extract_field_order, apply_patch, apply_patches


# ── find_entry_spans ────────────────────────────────────────────────


class TestFindEntrySpans:
    def test_single_entry(self):
        text = "@article{key1,\n  title={Hello},\n  year={2020}\n}"
        spans = find_entry_spans(text)
        assert len(spans) == 1
        assert spans[0][0] == "key1"
        assert text[spans[0][1] : spans[0][2]] == text

    def test_skips_string_preamble(self):
        text = '@string{neurips = {NeurIPS}}\n\n@preamble{"test"}\n\n@article{k,\n  title={T}\n}'
        spans = find_entry_spans(text)
        assert len(spans) == 1
        assert spans[0][0] == "k"

    def test_skips_commented_entries(self):
        text = "% @article{old,\n%   title={Old}\n% }\n\n@article{new,\n  title={New}\n}"
        spans = find_entry_spans(text)
        assert len(spans) == 1
        assert spans[0][0] == "new"

    def test_multiple_entries(self):
        text = "@article{a,\n  title={A}\n}\n\n@inproceedings{b,\n  title={B}\n}"
        spans = find_entry_spans(text)
        assert len(spans) == 2
        assert spans[0][0] == "a"
        assert spans[1][0] == "b"


# ── _extract_field_order ────────────────────────────────────────────


class TestExtractFieldOrder:
    def test_basic(self):
        raw = "@article{k,\n  title={T},\n  author={A},\n  year={2020}\n}"
        assert _extract_field_order(raw) == ["title", "author", "year"]

    def test_with_extra_whitespace(self):
        raw = "@article{k,\n  title = {T},\n  year={2020}\n}"
        assert _extract_field_order(raw) == ["title", "year"]


# ── _compute_field_order ────────────────────────────────────────────


class TestComputeFieldOrder:
    def test_preserves_order(self):
        order = _compute_field_order(["title", "author", "year"], {"title": "T", "author": "A", "year": "2020"})
        assert order == ["title", "author", "year"]

    def test_venue_swap(self):
        order = _compute_field_order(["title", "journal", "year"], {"title": "T", "booktitle": "Conf", "year": "2020"})
        assert order == ["title", "booktitle", "year"]

    def test_new_field_appended(self):
        order = _compute_field_order(["title", "year"], {"title": "T", "year": "2020", "volume": "1"})
        assert order == ["title", "year", "volume"]

    def test_removed_field_skipped(self):
        order = _compute_field_order(["title", "publisher", "year"], {"title": "T", "year": "2020"})
        assert order == ["title", "year"]


# ── _comment_out ────────────────────────────────────────────────────


class TestCommentOut:
    def test_basic(self):
        assert comment_out("@article{k,\n  title={T}\n}") == ("% @article{k,\n%   title={T}\n% }")


# ── _build_entry ────────────────────────────────────────────────────


class TestBuildEntry:
    def test_basic(self):
        result = _build_entry("article", "k", {"title": "T", "year": "2020"}, ["title", "year"])
        assert result == "@article{k,\n  title={T},\n  year={2020}\n}"

    def test_single_field_no_trailing_comma(self):
        result = _build_entry("article", "k", {"title": "T"}, ["title"])
        assert result == "@article{k,\n  title={T}\n}"


# ── apply_patch ─────────────────────────────────────────────────────


class TestApplyPatch:
    RAW = "@article{k,\n  title={Old Title},\n  author={Smith, John},\n  year={2020}\n}"
    PARSED = {"entry_type": "article", "key": "k", "title": "Old Title", "author": "Smith, John", "year": "2020"}

    def test_not_found(self):
        result = apply_patch(self.RAW, self.PARSED, {"key": "k", "action": "not_found"})
        assert result.startswith("% bibtidy: NOT FOUND")
        assert "% @article{k," in result
        # No active entry
        assert "\n@" not in result

    def test_duplicate(self):
        result = apply_patch(self.RAW, self.PARSED, {"key": "k", "action": "duplicate", "duplicate_of": "other"})
        assert result.startswith("% bibtidy: DUPLICATE of other")
        assert "@article{k," in result
        # Original entry preserved (not commented)
        entry_lines = [line for line in result.split("\n") if line.startswith("@")]
        assert len(entry_lines) == 1

    def test_fix_updates_fields(self):
        result = apply_patch(
            self.RAW,
            self.PARSED,
            {
                "key": "k",
                "action": "fix",
                "urls": ["https://example.com"],
                "explanation": "updated title",
                "fields": {"title": "New Title"},
            },
        )
        assert "% @article{k," in result
        assert "% bibtidy: https://example.com" in result
        assert "% bibtidy: updated title" in result
        assert "title={New Title}" in result
        # Original fields preserved
        assert "author={Smith, John}" in result
        assert "year={2020}" in result

    def test_fix_removes_field(self):
        result = apply_patch(
            self.RAW,
            self.PARSED,
            {
                "key": "k",
                "action": "fix",
                "urls": ["https://example.com"],
                "explanation": "removed author",
                "fields": {"author": None},
            },
        )
        # Corrected entry should not have author
        corrected = result.split("% bibtidy: removed author\n")[1]
        assert "author=" not in corrected

    def test_fix_changes_entry_type(self):
        result = apply_patch(
            self.RAW,
            self.PARSED,
            {
                "key": "k",
                "action": "fix",
                "urls": ["https://example.com"],
                "explanation": "type change",
                "entry_type": "inproceedings",
                "fields": {},
            },
        )
        assert "@inproceedings{k," in result

    def test_fix_venue_swap(self):
        raw = "@article{k,\n  title={T},\n  journal={arXiv},\n  year={2020}\n}"
        parsed = {"entry_type": "article", "key": "k", "title": "T", "journal": "arXiv", "year": "2020"}
        result = apply_patch(
            raw,
            parsed,
            {
                "key": "k",
                "action": "fix",
                "urls": ["https://example.com"],
                "explanation": "published",
                "entry_type": "inproceedings",
                "fields": {"journal": None, "booktitle": "ICLR", "year": "2023"},
            },
        )
        # booktitle should appear where journal was (before year)
        corrected_lines = result.split("% bibtidy: published\n")[1].split("\n")
        field_lines = [line.strip() for line in corrected_lines if "=" in line]
        field_names = [line.split("=")[0].strip() for line in field_lines]
        assert field_names == ["title", "booktitle", "year"]

    def test_fix_urls_sorted_and_deduplicated(self):
        result = apply_patch(
            self.RAW,
            self.PARSED,
            {
                "key": "k",
                "action": "fix",
                "urls": ["https://example.com/b", "https://example.com/a", "https://example.com/b"],
                "explanation": "test",
                "fields": {"title": "New"},
            },
        )
        url_lines = [line for line in result.split("\n") if line.startswith("% bibtidy: https://")]
        assert len(url_lines) == 2
        assert url_lines[0] == "% bibtidy: https://example.com/a"
        assert url_lines[1] == "% bibtidy: https://example.com/b"


# ── apply_patches (integration) ────────────────────────────────────


class TestApplyPatches:
    def test_preserves_unchanged_entries(self):
        text = "@article{a,\n  title={A}\n}\n\n@article{b,\n  title={B}\n}"
        result, applied = apply_patches(text, [])
        assert result == text
        assert applied == set()

    def test_mixed_actions(self):
        text = "@article{a,\n  title={A}\n}\n\n@article{b,\n  title={B}\n}\n\n@article{c,\n  title={C}\n}"
        patches = [{"key": "a", "action": "not_found"}, {"key": "c", "action": "duplicate", "duplicate_of": "a"}]
        result, applied = apply_patches(text, patches)
        assert applied == {"a", "c"}
        # a is commented out
        assert "% @article{a," in result
        # b is unchanged
        assert "@article{b," in result
        # c has duplicate flag
        assert "% bibtidy: DUPLICATE of a" in result
        assert "@article{c," in result

    def test_preserves_string_blocks(self):
        text = "@string{x = {Y}}\n\n@article{k,\n  title={T}\n}"
        patches = [
            {"key": "k", "action": "fix", "urls": ["https://x.com"], "explanation": "test", "fields": {"title": "New"}}
        ]
        result, applied = apply_patches(text, patches)
        assert applied == {"k"}
        assert "@string{x = {Y}}" in result
        assert "title={New}" in result

    def test_unknown_key_not_in_applied(self, capsys):
        text = "@article{a,\n  title={A}\n}"
        patches = [{"key": "nonexistent", "action": "not_found"}]
        result, applied = apply_patches(text, patches)
        assert applied == set()
        assert result == text
        assert "nonexistent" in capsys.readouterr().err

    def test_duplicate_keys_patches_both(self):
        text = "@article{k,\n  title={First}\n}\n\n@article{k,\n  title={Second}\n}"
        patches = [{"key": "k", "action": "not_found"}]
        result, applied = apply_patches(text, patches)
        assert applied == {"k"}
        # Both entries with the same key should be patched
        assert result.count("% bibtidy: NOT FOUND") == 2
