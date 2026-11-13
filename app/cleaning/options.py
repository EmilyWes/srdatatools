from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.db.settings import delete_setting, get_setting, set_setting
from app.parsers.mapping import DateOrder
from app.parsers.profiles.overview import QuirkBox, QuirkItem, QuirkList

_OPTIONS_KEY = "cleaning_options"


class CleaningOptions(BaseModel):
    strip_extras: bool = True
    only_one: bool = True
    preferred_qualifier: str = "Electronic"
    drop_et_al: bool = True
    drop_trailing: bool = True
    split_authors: bool = True
    names_separator: str = ""
    affiliations_separator: str = ""
    ids_separator: str = ""
    id_from_name: bool = True
    author_strip_extras: bool = True
    affiliation_start: str = ", "
    split_keywords: bool = True
    clean_dates: bool = True
    date_order: DateOrder = "eu"
    keywords_separator: str = ""
    empty_values: list[str] = ["[Not Available].", "none", "unknown"]
    refill_from_raw: bool = True
    strip_doi: bool = True
    strip_pmid: bool = True
    pages_set: bool = True
    first_publication_type: bool = True
    standardize_publication_type: bool = True
    ris_notes: bool = True
    eid_from_url: bool = True
    citation_parts: bool = True


def load_options(session: Session) -> CleaningOptions:
    stored = get_setting(session, _OPTIONS_KEY)
    if stored is None:
        return CleaningOptions()
    try:
        return CleaningOptions.model_validate_json(stored)
    except ValidationError:
        return CleaningOptions()


def save_options(session: Session, options: CleaningOptions) -> None:
    set_setting(session, _OPTIONS_KEY, options.model_dump_json())


def reset_options(session: Session) -> None:
    delete_setting(session, _OPTIONS_KEY)


_ISSN_ISBN = QuirkBox(
    "ISSN/ISBN",
    (
        QuirkItem(
            "strip_extras",
            "Strip extras",
            "The value might have qualifiers like (electronic) or (ISSN); strips"
            " everything away and keeps only the pure ISSN (8 digits) or ISBN"
            " (10 or 13 digits).",
            "checkbox",
        ),
        QuirkItem(
            "only_one",
            "Only keep one",
            "Some values hold several ISSNs or ISBNs; keeps only one of them:"
            " the first, unless the preferred qualifier picks another.",
            "checkbox",
        ),
        QuirkItem(
            "preferred_qualifier",
            "Preferred qualifier",
            "If a value is followed by a label in brackets, e.g."
            ' "1234-5678 (electronic), 9123-4567 (print)", fill in electronic to'
            " prefer the electronic value. Not case-sensitive.",
            "text",
            enabled_by="only_one",
        ),
    ),
)
_AUTHORS = QuirkBox(
    "Authors",
    (
        QuirkItem(
            "drop_et_al",
            'Drop "et al."',
            'Removes a trailing "et al." from the author names.',
            "checkbox",
        ),
        QuirkItem(
            "drop_trailing",
            "Drop trailing",
            "Removes non-name characters, like ... or ;, from the end of the last"
            " author's name. A full stop is only removed after a word of three or"
            " more letters, so initials like J. are kept.",
            "checkbox",
        ),
        QuirkItem(
            "split_authors",
            "Split authors",
            "Separates the author names, affiliations and IDs with |, so each"
            " author can be told apart. Needed for the options below.",
            "checkbox",
        ),
        QuirkItem(
            "names_separator",
            "Names separator",
            "What separates the author names in the imported value. Leave empty"
            " to detect it per imported file (|, ;, a line break or ' and ';"
            " never a comma, which also separates last and first names).",
            "text",
            enabled_by="split_authors",
        ),
        QuirkItem(
            "affiliations_separator",
            "Affiliations separator",
            "What separates the affiliations in the imported value. Leave empty"
            " to detect it per imported file, as for the names.",
            "text",
            enabled_by="split_authors",
        ),
        QuirkItem(
            "ids_separator",
            "IDs separator",
            "What separates the author IDs in an imported column, e.g. Scopus's"
            " Author(s) ID. Leave empty to detect it per imported file, as for"
            " the names.",
            "text",
            enabled_by="split_authors",
        ),
        QuirkItem(
            "id_from_name",
            "Scopus ID from name",
            "Scopus adds the author ID to the name (Doe, John (12345)); removes it"
            " from the name and adds it to the author IDs as scopus_author_id.",
            "checkbox",
            enabled_by="split_authors",
        ),
        QuirkItem(
            "author_strip_extras",
            "Strip extras",
            "Removes trailing text in brackets from each author name, e.g."
            " Doe, John (12345) becomes Doe, John. The removed text is not kept.",
            "checkbox",
            enabled_by="split_authors",
        ),
        QuirkItem(
            "affiliation_start",
            "Affiliation start",
            "Sometimes an affiliation starts with the author's name; strips"
            " everything up to this delimiter, if the text before it is that"
            " author's last name plus initials. Such an affiliation without the"
            " delimiter is only a name and is dropped. Leave empty to keep"
            " affiliations as they are.",
            "text",
            enabled_by="split_authors",
        ),
    ),
)
_KEYWORDS = QuirkBox(
    "Keywords",
    (
        QuirkItem(
            "split_keywords",
            "Split keywords",
            "Splits each imported keywords value into separate keywords, keeping"
            " its prefix.",
            "checkbox",
        ),
        QuirkItem(
            "keywords_separator",
            "Keywords separator",
            "What separates the keywords in the imported value. Leave empty to"
            " detect it per imported file, as for the author names.",
            "text",
            enabled_by="split_keywords",
        ),
    ),
)
_DATES = QuirkBox(
    "Dates",
    (
        QuirkItem(
            "clean_dates",
            "Clean up dates",
            "Reads the publication date and writes it as YYYY/MM/DD, an unknown"
            " part left empty (1994//). A date that can't be read is kept as it"
            " is.",
            "checkbox",
        ),
        QuirkItem(
            "date_order",
            "Ambiguous dates",
            "Which number is the month in a numeric date like 03/04/2020 where"
            " both could be.",
            "select",
            enabled_by="clean_dates",
            choices={"eu": "Day before month (EU)", "us": "Month before day (US)"},
        ),
    ),
)
_EMPTY_VALUES = QuirkBox(
    "Empty values",
    (
        QuirkList(
            "empty_values",
            (
                QuirkItem(
                    "value",
                    "Ignore",
                    "Values that count as empty in any text field. Not"
                    " case-sensitive.",
                    "text",
                    wide=True,
                ),
            ),
        ),
        QuirkItem(
            "refill_from_raw",
            "Refill from raw",
            "Fills a field emptied above from the next imported column mapped to"
            " that field, if there is one.",
            "checkbox",
        ),
    ),
)
_IDENTIFIERS = QuirkBox(
    "Identifiers",
    (
        QuirkItem(
            "strip_doi",
            "Strip DOI",
            'Strips all extra text from a DOI, leaving e.g. "10.1038/nature12373".',
            "checkbox",
        ),
        QuirkItem(
            "strip_pmid",
            "Strip PMID",
            "Strips all extra text from PMIDs, keeping only the number.",
            "checkbox",
        ),
    ),
)
_OTHER = QuirkBox(
    "Other",
    (
        QuirkItem(
            "pages_set",
            "Pages set",
            "Expands a page range like 512-4 to 512-514. Only acts if the second"
            " value is lower than the first.",
            "checkbox",
        ),
        QuirkItem(
            "first_publication_type",
            "First pub. type",
            "NBIB can have several lines for publication type; keeps only the"
            " first.",
            "checkbox",
        ),
        QuirkItem(
            "standardize_publication_type",
            "Standardize pub. type",
            "Maps vendor publication types to one list, e.g. JOUR, article and"
            " Journal Article become Journal article. Not case-sensitive. A type"
            " that isn't on the list keeps its text.",
            "checkbox",
        ),
    ),
)
_FROM_FILE = QuirkBox(
    "From raw fields",
    (
        QuirkItem(
            "ris_notes",
            "Values in RIS notes",
            "Scopus packs labelled values into N1 note lines (EID: 2-s2.0-…);"
            " reads them into their fields, even when N1 was set to ignore. A"
            " filled field is kept; an other ID is always set.",
            "checkbox",
        ),
        QuirkItem(
            "eid_from_url",
            "Scopus EID from URL",
            "Scopus BibTeX has no EID field, but its url links the record; reads"
            " the EID from it, even when url was set to ignore.",
            "checkbox",
        ),
        QuirkItem(
            "citation_parts",
            "Values from Citation",
            "PubMed CSV packs volume, issue and pages into its Citation column"
            " (Nature. 2023 Aug;620(7974):589-594.); reads them into fields that"
            " are still empty, even when Citation was set to ignore. Only that"
            " plain form is read.",
            "checkbox",
        ),
    ),
)

CLEANING_BOXES = [
    _ISSN_ISBN,
    _KEYWORDS,
    _DATES,
    _IDENTIFIERS,
    _OTHER,
    _FROM_FILE,
    _AUTHORS,
    _EMPTY_VALUES,
]
