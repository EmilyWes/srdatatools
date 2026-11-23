from app.helpers.format import (
    author_id_key,
    author_id_name,
    format_count,
    is_author_id_key,
    is_keyword_key,
    is_label_key,
    keyword_key,
    keyword_prefix,
    label_key,
    label_pair,
)


def test_format_count__dot_thousands_separator() -> None:
    assert format_count(25694) == "25.694"
    assert format_count(1234567) == "1.234.567"
    assert format_count(999) == "999"


def test_label_key__round_trips_phase_and_screener() -> None:
    key = label_key("ft", "screener: 1")

    assert is_label_key(key)
    assert not is_keyword_key(key)
    assert label_pair(key) == ("ft", "screener: 1")


def test_keyword_key__round_trips_prefix_and_unprefixed() -> None:
    assert is_keyword_key(keyword_key("MeSH"))
    assert keyword_prefix(keyword_key("MeSH")) == "MeSH"
    assert keyword_prefix(keyword_key(None)) is None


def test_author_id_key__round_trips_key() -> None:
    key = author_id_key("orcid")

    assert is_author_id_key(key)
    assert not is_author_id_key("author_ids")
    assert not is_keyword_key(key)
    assert author_id_name(key) == "orcid"
