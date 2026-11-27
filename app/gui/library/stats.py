from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from app.db.record import list_record_rows
from app.gui.library.quality import CHECKS, QUALITY_FIELDS, quality_issues
from app.models.record import publication_year


def count_records_per_year(session: Session) -> list[tuple[int | None, int]]:
    counts = Counter(
        publication_year(row["publication_date"])
        for row in list_record_rows(session, ["publication_date"])
    )
    return sorted(counts.items(), key=lambda item: (item[0] is None, item[0] or 0))


def count_data_quality(session: Session) -> list[tuple[str, int]]:
    counts = Counter(
        issue
        for row in list_record_rows(session, QUALITY_FIELDS)
        for issue in quality_issues(row)
    )
    return [(name, counts[name]) for name in CHECKS]


def count_keywords(session: Session) -> dict[str | None, list[tuple[str, int]]]:
    """Grouped case-insensitively; the first spelling seen is shown. Unprefixed
    keywords are under None."""
    spellings: dict[tuple[str | None, str], str] = {}
    counts: dict[str | None, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in list_record_rows(session, ["keywords"]):
        seen = set()
        for stored_prefix, texts in row["keywords"].items():
            for text in texts:
                prefix = stored_prefix or None
                key = (prefix, text.casefold())
                if key in seen:
                    continue
                seen.add(key)
                spelling = spellings.setdefault(key, text)
                counts[prefix][spelling] += 1
    return {
        prefix: sorted(texts.items(), key=lambda item: (-item[1], item[0].casefold()))
        for prefix, texts in counts.items()
    }


def list_keyword_prefixes(session: Session) -> list[str]:
    return [prefix for prefix in count_keywords(session) if prefix is not None]


def list_author_id_keys(session: Session) -> list[str]:
    rows = list_record_rows(session, ["author_ids"])
    return list(dict.fromkeys(key for row in rows for key in row["author_ids"]))


def count_publication_types(session: Session) -> list[tuple[str | None, int]]:
    """Grouped case-insensitively; the first spelling seen is shown. Empty is None."""
    spellings: dict[str, str] = {}
    counts: Counter[str | None] = Counter()
    for row in list_record_rows(session, ["publication_type"]):
        value = row["publication_type"]
        if not value:
            counts[None] += 1
            continue
        counts[spellings.setdefault(value.casefold(), value)] += 1
    return sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0] is None, (item[0] or "").casefold()),
    )
