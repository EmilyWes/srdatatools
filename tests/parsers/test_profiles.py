from app.parsers.mapping import Suggest
from app.parsers.profiles import FormatProfile, _layer, profile_for
from app.parsers.profiles.asreview import ASREVIEW
from app.parsers.profiles.base import never_matches
from app.parsers.profiles.default import (
    DEFAULT_PROFILES,
    default_settings,
)
from app.parsers.profiles.pubmed import PUBMED
from app.parsers.quirks import NO_QUIRKS, ParseSettings


def _format_profile(
    suggestions: dict[str, Suggest] | None = None,
    ignored_keys: frozenset[str] = frozenset(),
    settings: ParseSettings = NO_QUIRKS,
) -> FormatProfile:
    return FormatProfile(suggestions or {}, never_matches, settings, ignored_keys)


def test_profile_for__no_sources_returns_type_default() -> None:
    assert profile_for((), "nbib") is DEFAULT_PROFILES["nbib"]


def test_profile_for__one_source_has_its_aliases_and_settings() -> None:
    profile = profile_for(("pubmed",), "csv")

    assert profile is not None
    assert profile.suggestions == PUBMED.formats["csv"].suggestions
    assert profile.settings == PUBMED.formats["csv"].settings


def test_profile_for__source_without_that_format_returns_type_default() -> None:
    assert profile_for(("pubmed",), "ris") == DEFAULT_PROFILES["ris"]


def test_profile_for__unknown_source_key_is_skipped() -> None:
    assert profile_for(("unknown",), "nbib") == DEFAULT_PROFILES["nbib"]


def test_profile_for__unsupported_type_returns_none() -> None:
    assert profile_for((), "unknown") is None  # type: ignore[arg-type]


def test_profile_for__layers_vendor_then_asreview_whatever_the_given_order() -> None:
    profile = profile_for(("asreview", "scopus"), "ris")

    assert profile == profile_for(("scopus", "asreview"), "ris")
    assert profile is not None
    assert profile.suggestions["m3"] == Suggest("publication_type")
    assert profile.suggestions["n1"] == Suggest("label")
    assert profile.ignored_keys == frozenset({"ty"})
    assert profile.settings == ASREVIEW.formats["ris"].settings


def test_layer__top_alias_replaces_base_alias_of_the_same_key() -> None:
    base = _format_profile({"a": Suggest("title"), "b": Suggest("doi")})
    top = _format_profile({"a": Suggest("abstract")})

    layered = _layer(base, top, ParseSettings())

    assert layered.suggestions == {"a": Suggest("abstract"), "b": Suggest("doi")}


def test_layer__top_suggesting_a_base_ignored_key_unignores_it() -> None:
    base = _format_profile(ignored_keys=frozenset({"a", "b"}))
    top = _format_profile({"a": Suggest("title")}, ignored_keys=frozenset({"c"}))

    layered = _layer(base, top, ParseSettings())

    assert layered.ignored_keys == frozenset({"b", "c"})


def test_layer__only_settings_top_changes_from_the_default_override() -> None:
    base = _format_profile(settings=ParseSettings(label_values=(("x", "include"),)))
    top = _format_profile(settings=ParseSettings(use_first=("B",)))

    layered = _layer(base, top, ParseSettings())

    assert layered.settings == ParseSettings(
        label_values=(("x", "include"),), use_first=("B",)
    )


def test_default_profiles__use_the_plain_parse_settings_ris_reads_da_first() -> None:
    for file_type, profile in DEFAULT_PROFILES.items():
        use_first = ("DA",) if file_type == "ris" else ()
        assert profile.settings == ParseSettings(use_first=use_first)


def test_default_settings__overrides_the_type_default() -> None:
    settings = default_settings("nbib", label_values=(("-1", "exclude"),))

    assert settings.label_values == (("-1", "exclude"),)
