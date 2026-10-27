import logging
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

from app.models.record import Author
from app.parsers.authors import author_from_name
from app.parsers.common import (
    FileSummary,
    ParsedRow,
    ParseResult,
    SkippedRow,
    SummaryBuilder,
    decode_file,
)
from app.parsers.mapping import FieldMapping, apply_mapping, override_aliases
from app.parsers.mapping import suggest_mapping as _suggest_mapping

logger = logging.getLogger(__name__)

# Pseudo-keys: "@" can't start a real field name, so these never collide with one.
TYPE_KEY = "@type"
CITATION_KEY = "@key"

_SUGGESTION_ALIASES: dict[str, list[str]] = {
    "title": ["title"],
    "authors": ["author"],
    "abstract": ["abstract"],
    "journal": ["journal", "booktitle"],
    "volume": ["volume"],
    "issue": ["number"],
    "pages": ["pages"],
    "doi": ["doi"],
    "issn": ["issn"],
    "isbn": ["isbn"],
    "year": ["year"],
    "month": ["month"],
    "keywords": ["keywords"],
    "publisher": ["publisher"],
    "url": ["url"],
    "notes": ["note"],
    "language": ["language"],
    "publication_type": [TYPE_KEY],
}

_IGNORED_ENTRY_TYPES = frozenset({"comment", "string", "preamble"})
_ENTRY_START = re.compile(
    r"^[ \t]*@(?P<type>[A-Za-z]+)[ \t]*(?P<open>[{(])", re.MULTILINE
)
_CLOSERS = {"{": "}", "(": ")"}
# Scopus builds keys from page numbers, so pages "22,24" gives key "Wong200922,24".
_KEY_CONTINUATION = re.compile(r"[^\s=]+")

_PAGES_FIELD = "pages"
_PAGE_DASHES = re.compile(r"\s*-+\s*")
_LITERAL_DASH_FIELDS = frozenset({"url", "doi"})

_AUTHOR_SEPARATOR = re.compile(r"\s+and\s+", re.IGNORECASE)
_AUTHOR_FIELD = "author"
# BibTeX names are "Family, Given" or "Given Family"; only the first is split.
_NAME_SEPARATOR = ","

_COMBINING_ACCENTS = {
    '"': "\u0308",
    "'": "\u0301",
    "`": "\u0300",
    "^": "\u0302",
    "~": "\u0303",
    "=": "\u0304",
    ".": "\u0307",
    "c": "\u0327",
    "v": "\u030c",
    "u": "\u0306",
    "H": "\u030b",
    "k": "\u0328",
    "r": "\u030a",
}
_DOTLESS_I = re.compile(r"\\i(?![A-Za-z])")
_ACCENT = re.compile(
    r"\\(?:(?P<symbol>[\"'`^~=.])|(?P<word>[cvuHkr])(?![A-Za-z]))"
    r"\s*(?:\{(?P<braced>[A-Za-z])\}|(?P<bare>[A-Za-z]))"
)
_ESCAPED_SYMBOL = re.compile(r"\\([&%$#_])")
_COMMAND_ARGUMENT = re.compile(r"(\\[A-Za-z]+)\{")


@dataclass
class _Entry:
    line_number: int
    fields: list[tuple[str, str]]


@dataclass
class _MalformedEntry:
    line_number: int
    reason: str


def _decode_accent(match: re.Match[str]) -> str:
    accent = _COMBINING_ACCENTS[match["symbol"] or match["word"]]
    return unicodedata.normalize("NFC", (match["braced"] or match["bare"]) + accent)


def clean_value(field: str, value: str) -> str:
    if field == _PAGES_FIELD:
        value = _PAGE_DASHES.sub("-", value)
    value = _DOTLESS_I.sub("i", value)
    value = _ACCENT.sub(_decode_accent, value)
    value = _ESCAPED_SYMBOL.sub(r"\1", value)
    value = _COMMAND_ARGUMENT.sub(r"\1 ", value)
    value = " ".join(value.replace("{", "").replace("}", "").split())
    if field in _LITERAL_DASH_FIELDS:
        return value
    return value.replace("--", "\u2013")


def _top_level(text: str, wanted: str) -> Iterator[tuple[int, str]]:
    """Wanted characters outside braces and quotes, then the "}" that closes text.

    Only braces, quotes and wanted characters are visited: a per-character loop
    is too slow for large exports.
    """
    depth, quoted = 0, False
    for match in re.finditer('[{}"' + re.escape(wanted) + "]", text):
        index, char = match.start(), match.group()
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                yield index, char
                return
        elif char == '"' and depth == 0:
            quoted = not quoted
        elif depth == 0 and not quoted:
            yield index, char


def _split_top_level(text: str, separator: str) -> list[str]:
    cuts = [index for index, char in _top_level(text, separator) if char == separator]
    return [
        text[a + 1 : b] for a, b in zip([-1, *cuts], [*cuts, len(text)], strict=True)
    ]


def _strip_delimiters(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and (value[0], value[-1]) in (("{", "}"), ('"', '"')):
        return value[1:-1]
    return value


def _parse_entry(
    entry_type: str, body: str, line_number: int
) -> _Entry | _MalformedEntry:
    key, *pieces = _split_top_level(body, ",")
    while pieces and _KEY_CONTINUATION.fullmatch(pieces[0]):
        key += "," + pieces.pop(0)
    key = key.strip()
    if not key or "=" in key:
        return _MalformedEntry(line_number, "entry has no citation key")
    fields = [(TYPE_KEY, entry_type.lower()), (CITATION_KEY, key)]
    names: set[str] = set()
    for piece in pieces:
        if not piece.strip():
            continue
        name, separator, value = piece.partition("=")
        name = name.strip().lower()
        if not separator or not name:
            return _MalformedEntry(line_number, f"malformed field {piece.strip()!r}")
        if name in names:
            logger.warning(
                "Ignoring repeated %r field in BibTeX entry at line %d",
                name,
                line_number,
            )
            continue
        names.add(name)
        fields.append((name, _strip_delimiters(value)))
    if not names:
        return _MalformedEntry(line_number, "entry has no fields")
    return _Entry(line_number, fields)


def _iter_entries(text: str) -> Iterator[_Entry | _MalformedEntry]:
    """An entry runs to its closing bracket; reaching the next "@" first is unbalanced.

    Anything between entries is a comment in BibTeX, so it is ignored.
    """
    starts = list(_ENTRY_START.finditer(text))
    line_number, counted_to = 1, 0
    for match, next_match in zip_longest(starts, starts[1:]):
        if match["type"].lower() in _IGNORED_ENTRY_TYPES:
            continue
        line_number += text.count("\n", counted_to, match.start())
        counted_to = match.start()
        end = next_match.start() if next_match is not None else len(text)
        segment = text[match.end() : end]
        closer = _CLOSERS[match["open"]]
        close = next(
            (i for i, char in _top_level(segment, closer) if char == closer), None
        )
        if close is None:
            yield _MalformedEntry(line_number, "entry has unbalanced braces")
        else:
            yield _parse_entry(match["type"], segment[:close], line_number)


def _split_authors(value: str) -> list[str]:
    """Only an "and" outside braces separates names: {Barnes and Noble} is one."""
    names: list[str] = []
    depth, position, start = 0, 0, 0
    for match in _AUTHOR_SEPARATOR.finditer(value):
        between = value[position : match.start()]
        depth += between.count("{") - between.count("}")
        position = match.start()
        if depth == 0:
            names.append(value[start : match.start()])
            start = match.end()
    names.append(value[start:])
    return names


def _authors_from_fields(raw_fields: dict[str, str], keys: list[str]) -> list[Author]:
    return [
        author_from_name(name, _NAME_SEPARATOR)
        for key in keys
        for raw_name in _split_authors(raw_fields.get(key, ""))
        if (name := clean_value(_AUTHOR_FIELD, raw_name))
    ]


def parse_bibtex_record(
    lines: list[tuple[str, str]], mapping: FieldMapping
) -> ParsedRow:
    raw_fields = dict(lines)
    cleaned = {key: clean_value(key, value) for key, value in raw_fields.items()}
    record = apply_mapping(cleaned, mapping)
    author_keys = [k for k, t in mapping.targets.items() if t == "authors"]
    if author_keys:
        authors = _authors_from_fields(raw_fields, author_keys)
        record = record.model_copy(update={"authors": authors})
    return ParsedRow(record=record, raw_fields=raw_fields)


def parse_bibtex_text(text: str, mapping: FieldMapping) -> ParseResult:
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    for entry in _iter_entries(text):
        if isinstance(entry, _MalformedEntry):
            skipped.append(SkippedRow(entry.line_number, entry.reason))
            logger.warning(
                "Skipping BibTeX entry at line %d: %s", entry.line_number, entry.reason
            )
        else:
            rows.append(parse_bibtex_record(entry.fields, mapping))
    return ParseResult(rows=rows, skipped=skipped)


def parse_bibtex_file(path: Path, mapping: FieldMapping) -> ParseResult:
    return parse_bibtex_text(decode_file(path), mapping)


def read_bibtex_fields(path: Path) -> FileSummary:
    summary = SummaryBuilder()
    for entry in _iter_entries(decode_file(path)):
        if isinstance(entry, _Entry):
            for key, value in entry.fields:
                summary.add(key, value)
            summary.end_record()
    return summary.build()


def suggest_bibtex_mapping(
    keys: list[str], alias_overrides: dict[str, list[str]] | None = None
) -> FieldMapping:
    aliases = override_aliases(_SUGGESTION_ALIASES, alias_overrides or {})
    return _suggest_mapping(keys, aliases, lenient=False)
