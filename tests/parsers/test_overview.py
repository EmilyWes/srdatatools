import pytest

from app.parsers.profiles import PROFILES, profile_for
from app.parsers.profiles.overview import (
    ParsingChoices,
    QuirkItem,
    QuirkList,
    default_choices,
    dump_choices,
    load_choices,
    profile_with,
    quirk_boxes,
)
from app.parsers.profiles.scopus import EMBEDDED_AUTHOR_IDS, RIS_NOTES
from app.parsers.quirks import (
    AffiliationLeadingName,
    DropEtAl,
    EmptyValues,
    StripLastAuthorTrailing,
)

_ALL_TYPES = ("ris", "nbib", "csv", "tsv", "excel", "bibtex")


def _keys(file_type: str) -> list[str]:
    return [
        item.key
        for box in quirk_boxes(file_type, "Type")
        for item in box.items
        if isinstance(item, QuirkItem)
    ]


def _type_box_keys(file_type: str) -> list[str]:
    box = quirk_boxes(file_type, "Type")[-1]
    return [item.key for item in box.items if isinstance(item, QuirkItem)]


def _with(file_type: str, source: str = "unknown", **changes: object) -> ParsingChoices:
    return default_choices(file_type, source).model_copy(update=changes)


@pytest.mark.parametrize("source", ["unknown", *PROFILES], ids=["unknown", *PROFILES])
@pytest.mark.parametrize("file_type", _ALL_TYPES)
def test_profile_with__defaults_reproduce_the_profile(
    file_type: str, source: str
) -> None:
    profile = profile_for(source, file_type)

    assert profile_with(file_type, source) == profile
    assert profile_with(file_type, source, default_choices(file_type, source)) == (
        profile
    )


def test_quirk_boxes__titles_in_order_ending_with_the_type_label() -> None:
    titles = [box.title for box in quirk_boxes("ris", "RIS")]

    assert titles == [
        "ISSN/ISBN",
        "Authors",
        "Labeling",
        "Empty values",
        "Ordering",
        "Identifiers",
        "Other",
        "RIS",
    ]


@pytest.mark.parametrize("file_type", _ALL_TYPES)
def test_quirk_boxes__every_control_key_is_a_choice(file_type: str) -> None:
    for box in quirk_boxes(file_type, "Type"):
        for item in box.items:
            key = item.key
            if isinstance(item, QuirkItem) and item.control == "note":
                continue
            assert key in ParsingChoices.model_fields


def test_quirk_boxes__preferred_qualifier_is_enabled_by_only_one() -> None:
    [_, _, preferred] = quirk_boxes("csv", "CSV")[0].items

    assert isinstance(preferred, QuirkItem)
    assert preferred.enabled_by == "only_one"


def test_quirk_boxes__empty_values_and_ordering_are_lists() -> None:
    boxes = {box.title: box for box in quirk_boxes("csv", "CSV")}

    [empty] = boxes["Empty values"].items
    [order] = boxes["Ordering"].items

    assert isinstance(empty, QuirkList)
    assert [(p.label, p.control) for p in empty.parts] == [
        ("Field", "select"),
        ("Ignore", "text"),
    ]
    assert isinstance(order, QuirkList)
    assert [(p.label, p.control) for p in order.parts] == [("Use first", "select")]


def test_quirk_boxes__type_box_per_type() -> None:
    assert _type_box_keys("csv") == ["field_size_limit", "author_columns"]
    assert _type_box_keys("tsv") == ["field_size_limit", "author_columns"]
    assert _type_box_keys("excel") == ["author_columns"]
    assert _type_box_keys("nbib") == ["first_publication_type"]
    assert _type_box_keys("ris") == [
        "ris_notes",
        "ris.author_details",
        "ris.outside_text",
    ]
    assert _type_box_keys("bibtex") == [
        "author_columns",
        "eid_from_url",
        "bibtex.key_continuation",
    ]


def test_quirk_boxes__type_specific_items_only_in_their_type() -> None:
    assert "field_size_limit" not in _keys("excel")
    assert "first_publication_type" not in _keys("ris")
    assert "ris_notes" not in _keys("bibtex")


def test_default_choices__unknown_source_defaults() -> None:
    choices = default_choices("csv", "unknown")

    assert choices.strip_extras and choices.only_one
    assert choices.preferred_qualifier == ""
    assert choices.drop_et_al and choices.strip_doi and choices.strip_pmid
    assert choices.pages_set and choices.minus_one_unlabeled
    assert not (choices.drop_trailing or choices.id_from_name)
    assert choices.affiliation_start == ""
    assert choices.name_split == "none"
    assert choices.empty_values == [("title", "[Not Available].")]
    assert choices.use_first == []
    assert choices.field_size_limit == 1_000_000
    assert choices.label_values == []


def test_default_choices__selected_profile_sets_its_own_quirks() -> None:
    scopus = default_choices("csv", "scopus")

    assert scopus.id_from_name
    assert scopus.affiliation_start == ", "
    assert not scopus.drop_trailing
    assert default_choices("csv", "pubmed").drop_trailing
    assert default_choices("ris", "scopus").ris_notes
    assert not default_choices("ris", "unknown").ris_notes
    assert default_choices("bibtex", "scopus").eid_from_url


def test_default_choices__nbib_prefers_electronic_and_keeps_first_type() -> None:
    choices = default_choices("nbib", "unknown")

    assert choices.preferred_qualifier == "Electronic"
    assert choices.first_publication_type


def test_default_choices__unsupported_type_raises() -> None:
    with pytest.raises(ValueError):
        default_choices("unknown", "unknown")


def test_profile_with__turns_a_type_default_off() -> None:
    profile = profile_with("csv", "unknown", _with("csv", drop_et_al=False))

    assert DropEtAl() not in profile.quirks


def test_profile_with__turns_another_profiles_quirk_on() -> None:
    choices = _with("excel", id_from_name=True, affiliation_start="; ")

    profile = profile_with("excel", "unknown", choices)

    assert EMBEDDED_AUTHOR_IDS in profile.quirks
    assert AffiliationLeadingName("; ") in profile.quirks


def test_profile_with__ris_notes_on_for_any_ris_source() -> None:
    profile = profile_with("ris", "unknown", _with("ris", ris_notes=True))

    assert RIS_NOTES in profile.quirks


def test_profile_with__empty_affiliation_start_is_off() -> None:
    choices = _with("csv", "scopus", affiliation_start="")

    quirks = profile_with("csv", "scopus", choices).quirks

    assert not any(isinstance(q, AffiliationLeadingName) for q in quirks)


def test_profile_with__id_from_name_runs_before_drop_trailing() -> None:
    choices = _with("csv", id_from_name=True, drop_trailing=True)

    quirks = profile_with("csv", "unknown", choices).quirks

    assert quirks.index(EMBEDDED_AUTHOR_IDS) < quirks.index(StripLastAuthorTrailing())
    assert quirks.index(DropEtAl()) < quirks.index(StripLastAuthorTrailing())


def test_profile_with__applies_the_settings() -> None:
    choices = _with(
        "csv",
        strip_extras=False,
        only_one=False,
        preferred_qualifier=" print ",
        minus_one_unlabeled=False,
        name_split="last",
        field_size_limit=500,
        use_first=["B", "A"],
    )

    settings = profile_with("csv", "unknown", choices).settings

    assert not settings.issn_isbn_strip_extras
    assert not settings.issn_isbn_only_one
    assert settings.preferred_issn_qualifier == "print"
    assert not settings.minus_one_unlabeled
    assert settings.ambiguous_name_split == "last"
    assert settings.csv_field_size_limit == 500
    assert settings.use_first == ("B", "A")


def test_profile_with__label_values_are_lowercased_and_blanks_dropped() -> None:
    choices = _with(
        "ris", label_values=[(" ASReview_relevant ", "include"), ("  ", "exclude")]
    )

    settings = profile_with("ris", "unknown", choices).settings

    assert settings.label_values == (("asreview_relevant", "include"),)


def test_profile_with__empty_preferred_qualifier_is_none() -> None:
    choices = _with("nbib", preferred_qualifier=" ")

    assert profile_with(
        "nbib", "unknown", choices
    ).settings.preferred_issn_qualifier is (None)


def test_profile_with__empty_values_are_pipe_separated() -> None:
    choices = _with(
        "ris", empty_values=[("title", "[Not Available]. | n/a |"), ("doi", "none")]
    )

    settings = profile_with("ris", "unknown", choices).settings

    assert settings.empty_values == (
        EmptyValues("title", frozenset({"[Not Available].", "n/a"})),
        EmptyValues("doi", frozenset({"none"})),
    )


def test_profile_with__empty_values_without_field_or_values_are_skipped() -> None:
    choices = _with("ris", empty_values=[("", "n/a"), ("title", " ")])

    assert profile_with("ris", "unknown", choices).settings.empty_values == ()


def test_dump_choices__round_trips() -> None:
    choices = _with("csv", "scopus", empty_values=[("title", "a|b")], use_first=["X"])

    assert load_choices(dump_choices(choices), "csv", "scopus") == choices


def test_load_choices__missing_keys_keep_the_profile_defaults() -> None:
    choices = load_choices({"drop_et_al": False}, "csv", "scopus")

    assert choices == _with("csv", "scopus", drop_et_al=False)


def test_load_choices__old_style_choices_fall_back_to_defaults() -> None:
    old = {
        "FirstValue.issn": {"on": True, "values": {"delimiter": ";"}},
        "minus_one_unlabeled": {"on": False, "values": {}},
    }

    assert load_choices(old, "ris", "unknown") == default_choices("ris", "unknown")
