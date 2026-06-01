"""Tests for the line-preserving .env document model."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotfill.envdoc import (
    AssignmentLine,
    BlankLine,
    CommentLine,
    EnvDocument,
    UnparsedLine,
    parse_content,
)
from dotfill.errors import EnvParseError


def test_parse_simple_assignment() -> None:
    doc = EnvDocument.from_text("FOO=bar\n")
    assert doc.get("FOO") == "bar"
    assert doc.keys() == ["FOO"]


def test_parse_multiple_assignments() -> None:
    doc = EnvDocument.from_text("A=1\nB=two\nC=3\n")
    assert doc.get("A") == "1"
    assert doc.get("B") == "two"
    assert doc.get("C") == "3"


def test_parse_double_quoted_value() -> None:
    doc = EnvDocument.from_text('FOO="hello world"\n')
    assert doc.get("FOO") == "hello world"
    ref = doc.find_assignments("FOO")[0]
    assert ref.assignment.quote_style == "double"


def test_parse_single_quoted_value() -> None:
    doc = EnvDocument.from_text("FOO='hello world'\n")
    assert doc.get("FOO") == "hello world"
    ref = doc.find_assignments("FOO")[0]
    assert ref.assignment.quote_style == "single"


def test_parse_double_quoted_escapes() -> None:
    doc = EnvDocument.from_text('FOO="line1\\nline2\\t\\"q\\""\n')
    assert doc.get("FOO") == 'line1\nline2\t"q"'


def test_parse_single_quoted_is_literal() -> None:
    doc = EnvDocument.from_text("FOO='no\\nescapes'\n")
    assert doc.get("FOO") == "no\\nescapes"


def test_preserves_comments_and_blanks_on_roundtrip() -> None:
    src = "# header comment\n\nFOO=bar\n# trailing\nBAR=baz\n\n"
    doc = EnvDocument.from_text(src)
    assert doc.render() == src


def test_preserves_unrelated_variables() -> None:
    src = "UNRELATED=keepme\nMANAGED=oldvalue\nOTHER=alsokeep\n"
    doc = EnvDocument.from_text(src)
    doc.set_value("MANAGED", "newvalue")
    rendered = doc.render()
    assert "UNRELATED=keepme" in rendered
    assert "OTHER=alsokeep" in rendered
    assert "MANAGED=newvalue" in rendered


def test_update_existing_key_in_place() -> None:
    src = "A=1\nFOO=old\nB=2\n"
    doc = EnvDocument.from_text(src)
    doc.set_value("FOO", "new")
    assert doc.render() == "A=1\nFOO=new\nB=2\n"


def test_update_preserves_quote_style_double() -> None:
    doc = EnvDocument.from_text('FOO="old value"\n')
    doc.set_value("FOO", "new value")
    assert doc.render() == 'FOO="new value"\n'


def test_update_preserves_quote_style_single() -> None:
    doc = EnvDocument.from_text("FOO='old'\n")
    doc.set_value("FOO", "new")
    assert doc.render() == "FOO='new'\n"


def test_append_missing_key() -> None:
    src = "A=1\n"
    doc = EnvDocument.from_text(src)
    doc.set_value("NEWKEY", "value")
    assert "NEWKEY=value" in doc.render()
    assert doc.render().startswith("A=1\n")


def test_append_quotes_value_with_spaces() -> None:
    doc = EnvDocument.from_text("")
    doc.set_value("FOO", "has spaces")
    rendered = doc.render()
    # Strip line ending differences across platforms
    assert rendered.rstrip("\r\n") == 'FOO="has spaces"'


def test_append_to_file_without_trailing_newline() -> None:
    doc = EnvDocument.from_text("A=1")
    doc.set_value("B", "2")
    rendered = doc.render()
    assert "A=1" in rendered
    assert "B=2" in rendered
    # Should have inserted a line ending before appending
    assert "A=1\nB=2" in rendered or "A=1\r\nB=2" in rendered


def test_preserves_unrelated_duplicate_variables() -> None:
    src = "DUP=one\nFOO=bar\nDUP=two\n"
    doc = EnvDocument.from_text(src)
    # No managed-set provided, so duplicates() returns empty
    assert doc.duplicates(set()) == {}
    # Round-trip preserves the duplicates
    assert doc.render() == src


def test_detects_duplicate_managed_variables_with_line_numbers() -> None:
    src = "SERVICE_A_TOKEN=a\nOTHER=x\nSERVICE_A_TOKEN=b\n"
    doc = EnvDocument.from_text(src)
    dups = doc.duplicates({"SERVICE_A_TOKEN"})
    assert dups == {"SERVICE_A_TOKEN": [1, 3]}


def test_preserves_crlf_line_endings() -> None:
    src = "A=1\r\nB=2\r\n"
    doc = EnvDocument.from_text(src)
    doc.set_value("A", "11")
    rendered = doc.render()
    assert rendered == "A=11\r\nB=2\r\n"


def test_appended_lines_use_dominant_line_ending_crlf() -> None:
    src = "A=1\r\n"
    doc = EnvDocument.from_text(src)
    doc.set_value("B", "2")
    assert doc.render() == "A=1\r\nB=2\r\n"


def test_new_file_content_is_deterministic() -> None:
    doc1 = EnvDocument(lines=[], path=None)
    doc1.set_value("A", "1")
    doc1.set_value("B", "2")
    doc2 = EnvDocument(lines=[], path=None)
    doc2.set_value("A", "1")
    doc2.set_value("B", "2")
    assert doc1.render() == doc2.render()


def test_unterminated_double_quote_is_unparsed() -> None:
    doc = EnvDocument.from_text('FOO="unterminated\n')
    unparsed = doc.unparsed_lines()
    assert len(unparsed) == 1
    assert "Unterminated" in unparsed[0].error


def test_export_prefix_preserved() -> None:
    src = "export FOO=bar\n"
    doc = EnvDocument.from_text(src)
    assert doc.get("FOO") == "bar"
    assert doc.render() == src


def test_inline_comment_preserved_on_unquoted() -> None:
    src = "FOO=bar # inline\n"
    doc = EnvDocument.from_text(src)
    assert doc.get("FOO") == "bar"
    assert doc.render() == src


def test_blank_line_recognized() -> None:
    lines = parse_content("\n   \nFOO=bar\n")
    assert isinstance(lines[0], BlankLine)
    assert isinstance(lines[1], BlankLine)
    assert isinstance(lines[2], AssignmentLine)


def test_comment_line_recognized() -> None:
    lines = parse_content("# a comment\n  # indented\n")
    assert all(isinstance(line, CommentLine) for line in lines)


def test_set_value_refuses_invalid_key() -> None:
    doc = EnvDocument.from_text("")
    with pytest.raises(ValueError):
        doc.set_value("1BAD", "x")


def test_set_value_refuses_duplicated_managed_key() -> None:
    doc = EnvDocument.from_text("FOO=a\nFOO=b\n")
    with pytest.raises(ValueError):
        doc.set_value("FOO", "c")


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    src = "A=1\n# c\nB=two\n"
    p.write_text(src, encoding="utf-8")
    doc = EnvDocument.from_path(p)
    doc.set_value("A", "11")
    doc.write()
    assert p.read_text(encoding="utf-8") == "A=11\n# c\nB=two\n"


def test_from_path_missing_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "absent.env"
    doc = EnvDocument.from_path(p)
    assert doc.lines == []
    assert doc.path == p


def test_has_non_empty() -> None:
    doc = EnvDocument.from_text("A=value\nB=\n")
    assert doc.has_non_empty("A")
    assert not doc.has_non_empty("B")
    assert not doc.has_non_empty("MISSING")
