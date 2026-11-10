from app.gui.format import (
    format_count,
    is_keyword_key,
    is_label_key,
    keyword_key,
    keyword_prefix,
    label_key,
    label_pair,
    source_label,
)


def test_source_label__uses_profile_label() -> None:
    assert source_label("pubmed") == "PubMed"


def test_source_label__unknown_for_none() -> None:
    assert source_label(None) == "Unknown"


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
