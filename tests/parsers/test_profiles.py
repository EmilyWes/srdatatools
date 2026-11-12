from app.parsers.mapping import RowDefaults
from app.parsers.profiles import has_profile, profile_for
from app.parsers.profiles.default import (
    DEFAULT_PROFILES,
    default_row_defaults,
    default_settings,
)
from app.parsers.profiles.pubmed import PUBMED
from app.parsers.quirks import ParseSettings


def test_profile_for__returns_format_profile_of_known_source() -> None:
    assert profile_for("pubmed", "nbib") is PUBMED.formats["nbib"]


def test_profile_for__source_without_that_format_returns_type_default() -> None:
    assert profile_for("pubmed", "ris") is DEFAULT_PROFILES["ris"]


def test_profile_for__unknown_source_returns_type_default() -> None:
    assert profile_for("unknown", "nbib") is DEFAULT_PROFILES["nbib"]


def test_profile_for__unsupported_type_returns_none() -> None:
    assert profile_for("unknown", "unknown") is None  # type: ignore[arg-type]


def test_has_profile__only_for_a_source_that_exports_the_type() -> None:
    assert has_profile("pubmed", "nbib")
    assert not has_profile("pubmed", "ris")
    assert not has_profile("unknown", "nbib")


def test_default_profiles__use_the_plain_parse_settings() -> None:
    for profile in DEFAULT_PROFILES.values():
        assert profile.settings == ParseSettings()


def test_default_settings__overrides_the_type_default() -> None:
    settings = default_settings("nbib", label_values=(("-1", "exclude"),))

    assert settings.label_values == (("-1", "exclude"),)


def test_default_profiles__use_each_types_row_defaults() -> None:
    assert DEFAULT_PROFILES["csv"].row_defaults == RowDefaults()
    assert DEFAULT_PROFILES["ris"].row_defaults == RowDefaults(delimiter="\n")
    assert DEFAULT_PROFILES["nbib"].row_defaults == RowDefaults(delimiter="\n")
    assert DEFAULT_PROFILES["bibtex"].row_defaults == RowDefaults(author_delimiter="\n")


def test_default_row_defaults__overrides_the_type_default() -> None:
    defaults = default_row_defaults("bibtex", delimiter=",")

    assert defaults == RowDefaults(delimiter=",", author_delimiter="\n")
