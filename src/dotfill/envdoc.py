"""Line-preserving `.env` document model.

Parses `.env` files into a list of typed lines (assignment, comment, blank,
unparsed) and supports targeted in-place updates while preserving comments,
blank lines, unrelated duplicates, quote styles, and line endings.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .errors import EnvParseError

# Conservative shell/env variable name pattern.
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Characters in an unquoted value that force us to add quotes when writing.
_NEEDS_QUOTE_RE = re.compile(r"[\s#'\"\\]")


def is_valid_var_name(name: str) -> bool:
    """Return True if name is a valid environment variable identifier."""
    return bool(_VAR_NAME_RE.match(name))


@dataclass
class EnvLine:
    """Base class for a parsed line."""

    raw: str
    line_ending: str
    line_number: int  # 1-based


@dataclass
class BlankLine(EnvLine):
    """A blank or whitespace-only line."""


@dataclass
class CommentLine(EnvLine):
    """A comment line (starts with `#`, optional leading whitespace)."""


@dataclass
class AssignmentLine(EnvLine):
    """A `KEY=value` assignment line.

    `leading` is whitespace before the key. `separator` is the `=` plus any
    inner whitespace (preserved verbatim). `value` is the unquoted value.
    `quote_style` records whether the source used single, double, or no quotes.
    `trailing_comment` is any inline `# ...` after the value (rare).
    """

    key: str
    value: str
    quote_style: str | None  # "single" | "double" | None
    leading: str = ""
    separator: str = "="
    trailing_comment: str | None = None
    # Optional `export ` prefix that we preserve verbatim.
    export_prefix: str = ""


@dataclass
class UnparsedLine(EnvLine):
    """A line that does not parse as anything we understand."""

    error: str


@dataclass
class AssignmentRef:
    """Reference returned by find_assignments — line index + the assignment."""

    index: int
    assignment: AssignmentLine


# Regex for an unquoted assignment line.
#   optional leading whitespace
#   optional "export " prefix
#   KEY (validated separately)
#   "=" possibly surrounded by spaces
#   value (any non-newline)
_ASSIGNMENT_RE = re.compile(
    r"""
    ^
    (?P<leading>[ \t]*)
    (?P<export>(?:export[ \t]+)?)
    (?P<key>[^\s=#][^=]*?)
    (?P<sep>[ \t]*=[ \t]*)
    (?P<value>.*?)
    [ \t]*
    $
    """,
    re.VERBOSE,
)


def _split_lines_keepending(text: str) -> list[tuple[str, str]]:
    """Split text into (content, line_ending) pairs.

    Recognizes CRLF, LF, and CR. The final line may have an empty line_ending
    if the file does not end with a newline.
    """
    out: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    start = 0
    while i < n:
        ch = text[i]
        if ch == "\r":
            if i + 1 < n and text[i + 1] == "\n":
                out.append((text[start:i], "\r\n"))
                i += 2
            else:
                out.append((text[start:i], "\r"))
                i += 1
            start = i
        elif ch == "\n":
            out.append((text[start:i], "\n"))
            i += 1
            start = i
        else:
            i += 1
    if start < n:
        out.append((text[start:n], ""))
    return out


def _parse_value(raw_value: str) -> tuple[str, str | None, str | None]:
    """Parse the value portion of an assignment.

    Returns (value, quote_style, trailing_comment).
    Raises EnvParseError on unterminated quotes.
    """
    s = raw_value
    if not s:
        return "", None, None

    first = s[0]
    if first == '"':
        # Double-quoted: support \" \\ \n \r \t escapes.
        result_chars: list[str] = []
        i = 1
        n = len(s)
        while i < n:
            c = s[i]
            if c == "\\" and i + 1 < n:
                nxt = s[i + 1]
                escape_map = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                result_chars.append(escape_map.get(nxt, nxt))
                i += 2
                continue
            if c == '"':
                # End of quoted value; rest must be whitespace or trailing comment.
                rest = s[i + 1 :].lstrip()
                trailing = None
                if rest:
                    if rest.startswith("#"):
                        trailing = rest
                    else:
                        raise EnvParseError(
                            f"Unexpected characters after quoted value: {rest!r}"
                        )
                return "".join(result_chars), "double", trailing
            result_chars.append(c)
            i += 1
        raise EnvParseError("Unterminated double-quoted value")
    if first == "'":
        # Single-quoted: literal, no escapes.
        end = s.find("'", 1)
        if end == -1:
            raise EnvParseError("Unterminated single-quoted value")
        value = s[1:end]
        rest = s[end + 1 :].lstrip()
        trailing = None
        if rest:
            if rest.startswith("#"):
                trailing = rest
            else:
                raise EnvParseError(
                    f"Unexpected characters after quoted value: {rest!r}"
                )
        return value, "single", trailing

    # Unquoted: strip trailing inline comment if present (` #...`).
    # python-dotenv splits at first ` #` or whole-line `#`.
    trailing_comment: str | None = None
    # Find ` #` or tab+#
    m = re.search(r"\s+#", s)
    if m:
        trailing_comment = s[m.start() :].lstrip()
        s = s[: m.start()]
    return s.rstrip(), None, trailing_comment


def parse_content(text: str) -> list[EnvLine]:
    """Parse `.env` text into a list of typed lines."""
    lines: list[EnvLine] = []
    parts = _split_lines_keepending(text)
    for i, (content, ending) in enumerate(parts, start=1):
        stripped = content.strip()
        if stripped == "":
            lines.append(BlankLine(raw=content, line_ending=ending, line_number=i))
            continue
        if stripped.startswith("#"):
            lines.append(CommentLine(raw=content, line_ending=ending, line_number=i))
            continue

        m = _ASSIGNMENT_RE.match(content)
        if not m:
            lines.append(
                UnparsedLine(
                    raw=content,
                    line_ending=ending,
                    line_number=i,
                    error="Not a valid assignment, comment, or blank line",
                )
            )
            continue

        key = m.group("key").strip()
        if not is_valid_var_name(key):
            lines.append(
                UnparsedLine(
                    raw=content,
                    line_ending=ending,
                    line_number=i,
                    error=f"Invalid variable name: {key!r}",
                )
            )
            continue

        try:
            value, quote_style, trailing = _parse_value(m.group("value"))
        except EnvParseError as exc:
            lines.append(
                UnparsedLine(
                    raw=content,
                    line_ending=ending,
                    line_number=i,
                    error=str(exc),
                )
            )
            continue

        lines.append(
            AssignmentLine(
                raw=content,
                line_ending=ending,
                line_number=i,
                key=key,
                value=value,
                quote_style=quote_style,
                leading=m.group("leading"),
                separator=m.group("sep"),
                trailing_comment=trailing,
                export_prefix=m.group("export"),
            )
        )
    return lines


def _needs_quoting(value: str) -> bool:
    if value == "":
        return False
    return bool(_NEEDS_QUOTE_RE.search(value))


def _render_value(value: str, quote_style: str | None) -> str:
    """Render a value with the requested quote style, falling back to double
    quotes if escaping is required.
    """
    if quote_style == "single":
        # Single quotes are literal — if the value contains a single quote,
        # escalate to double-quoted with escapes.
        if "'" in value or "\n" in value or "\r" in value:
            return _render_value(value, "double")
        return f"'{value}'"
    if quote_style == "double":
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'
    # No quotes — only acceptable if value does not need quoting.
    if _needs_quoting(value):
        return _render_value(value, "double")
    return value


def _render_line(line: EnvLine) -> str:
    if isinstance(line, AssignmentLine):
        rendered_value = _render_value(line.value, line.quote_style)
        trailing = f" {line.trailing_comment}" if line.trailing_comment else ""
        body = f"{line.leading}{line.export_prefix}{line.key}{line.separator}{rendered_value}{trailing}"
        return body + line.line_ending
    return line.raw + line.line_ending


@dataclass
class EnvDocument:
    """Line-preserving in-memory representation of a `.env` file."""

    lines: list[EnvLine] = field(default_factory=list)
    path: Path | None = None
    # Dominant line ending detected at parse time, used for newly appended lines.
    dominant_line_ending: str = field(default_factory=lambda: os.linesep)

    # ---- Construction --------------------------------------------------

    @classmethod
    def from_text(cls, text: str, *, path: Path | None = None) -> "EnvDocument":
        lines = parse_content(text)
        return cls(lines=lines, path=path, dominant_line_ending=_detect_line_ending(lines))

    @classmethod
    def from_path(cls, path: Path) -> "EnvDocument":
        if not path.exists():
            return cls(lines=[], path=path, dominant_line_ending=os.linesep)
        text = path.read_text(encoding="utf-8")
        return cls.from_text(text, path=path)

    # ---- Lookup --------------------------------------------------------

    def keys(self) -> list[str]:
        """Return keys in source order (with duplicates collapsed to first occurrence)."""
        seen: set[str] = set()
        out: list[str] = []
        for line in self.lines:
            if isinstance(line, AssignmentLine) and line.key not in seen:
                seen.add(line.key)
                out.append(line.key)
        return out

    def find_assignments(self, key: str) -> list[AssignmentRef]:
        """Return all assignments matching key (in source order)."""
        return [
            AssignmentRef(index=i, assignment=line)
            for i, line in enumerate(self.lines)
            if isinstance(line, AssignmentLine) and line.key == key
        ]

    def get(self, key: str) -> str | None:
        """Return the value of the first assignment matching key, or None."""
        refs = self.find_assignments(key)
        if not refs:
            return None
        return refs[0].assignment.value

    def has_non_empty(self, key: str) -> bool:
        v = self.get(key)
        return v is not None and v != ""

    # ---- Mutation ------------------------------------------------------

    def set_value(self, key: str, value: str) -> None:
        """Update an existing assignment in place, or append a new one.

        Refuses to update a key that exists more than once (defense against
        states that should have been blocked at startup).
        """
        if not is_valid_var_name(key):
            raise ValueError(f"Invalid variable name: {key!r}")
        refs = self.find_assignments(key)
        if len(refs) > 1:
            raise ValueError(
                f"Refusing to update {key!r}: defined {len(refs)} times in document"
            )
        if len(refs) == 1:
            existing = refs[0].assignment
            existing.value = value
            # If quote_style was None but value now needs quoting, _render_value
            # promotes to double-quoted automatically.
            return
        self._append(key, value)

    def set_values(self, changes: Mapping[str, str]) -> None:
        for k, v in changes.items():
            self.set_value(k, v)

    def _append(self, key: str, value: str) -> None:
        ending = self.dominant_line_ending or os.linesep
        # Ensure the last existing line has a line ending; if it does not,
        # promote it so our new line starts on its own row.
        if self.lines:
            last = self.lines[-1]
            if last.line_ending == "":
                last.line_ending = ending
        self.lines.append(
            AssignmentLine(
                raw="",
                line_ending=ending,
                line_number=len(self.lines) + 1,
                key=key,
                value=value,
                quote_style=None,
                leading="",
                separator="=",
                trailing_comment=None,
                export_prefix="",
            )
        )

    # ---- Rendering -----------------------------------------------------

    def render(self) -> str:
        return "".join(_render_line(line) for line in self.lines)

    def write(self, path: Path | None = None) -> Path:
        """Write the document to disk and return the target path."""
        target = path if path is not None else self.path
        if target is None:
            raise ValueError("No path provided for write()")
        target.write_text(self.render(), encoding="utf-8", newline="")
        return target

    # ---- Diagnostics ---------------------------------------------------

    def duplicates(self, managed_keys: Iterable[str]) -> dict[str, list[int]]:
        """Return {key: [line_numbers...]} for managed keys defined more than once."""
        managed = set(managed_keys)
        counts: dict[str, list[int]] = {}
        for line in self.lines:
            if isinstance(line, AssignmentLine) and line.key in managed:
                counts.setdefault(line.key, []).append(line.line_number)
        return {k: nums for k, nums in counts.items() if len(nums) > 1}

    def unparsed_lines(self) -> list[UnparsedLine]:
        return [line for line in self.lines if isinstance(line, UnparsedLine)]


def _detect_line_ending(lines: list[EnvLine]) -> str:
    """Pick a dominant line ending from parsed lines.

    Prefer the first assignment line's ending; otherwise the first line's
    ending; otherwise the OS default.
    """
    for line in lines:
        if isinstance(line, AssignmentLine) and line.line_ending:
            return line.line_ending
    for line in lines:
        if line.line_ending:
            return line.line_ending
    return os.linesep
