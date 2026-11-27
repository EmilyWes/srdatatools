import re

from app.gui.cleaning.steps import STANDARD_PUBLICATION_TYPE
from app.parsers.mapping import LINE_DELIMITER

TAG_PATTERN = re.compile(r"[A-Z][A-Z0-9]")

CURATED_TAGS: dict[str, str] = {
    "TY": "Type of reference",
    "TI": "Title",
    "T2": "Secondary title (journal / conference)",
    "J2": "Alternate title (journal abbreviation)",
    "AU": "Author",
    "A2": "Secondary author (editor)",
    "AD": "Author address / affiliation",
    "PY": "Publication year",
    "DA": "Date",
    "VL": "Volume",
    "IS": "Issue",
    "SP": "Start page",
    "EP": "End page",
    "AB": "Abstract",
    "DO": "DOI",
    "SN": "ISSN / ISBN",
    "KW": "Keyword",
    "LA": "Language",
    "PB": "Publisher",
    "CY": "Place published",
    "UR": "URL",
    "N1": "Notes",
    "AN": "Accession number",
    "ID": "Reference ID",
    "M3": "Type of work",
}
# ER only ends a record, so it isn't offered.
RIS_TAG_TO_NAME: dict[str, str] = {
    **CURATED_TAGS,
    "A1": "Primary author",
    "A3": "Tertiary author",
    "A4": "Subsidiary author",
    "AV": "Location in archives",
    "BT": "Book title",
    "C1": "Custom 1",
    "C2": "Custom 2",
    "C3": "Custom 3",
    "C4": "Custom 4",
    "C5": "Custom 5",
    "C6": "Custom 6",
    "C7": "Custom 7",
    "C8": "Custom 8",
    "CA": "Caption",
    "CN": "Call number",
    "CT": "Title of unpublished reference",
    "DB": "Name of database",
    "DP": "Database provider",
    "ED": "Editor",
    "ET": "Edition",
    "J1": "Periodical name: user abbreviation",
    "JA": "Periodical name: standard abbreviation",
    "JF": "Periodical name: full",
    "JO": "Journal name",
    "L1": "Link to PDF",
    "L2": "Link to full text",
    "L3": "Related records",
    "L4": "Images",
    "LB": "Label",
    "M1": "Miscellaneous 1",
    "M2": "Miscellaneous 2",
    "N2": "Abstract (older tag)",
    "NV": "Number of volumes",
    "OP": "Original publication",
    "RI": "Reviewed item",
    "RN": "Research notes",
    "RP": "Reprint edition",
    "SE": "Section",
    "ST": "Short title",
    "T1": "Primary title",
    "T3": "Tertiary title",
    "TA": "Translated author",
    "TT": "Translated title",
    "U1": "User definable 1",
    "U2": "User definable 2",
    "U3": "User definable 3",
    "U4": "User definable 4",
    "U5": "User definable 5",
    "Y1": "Primary date",
    "Y2": "Access date",
}

RIS_FIELD_TO_TAG: dict[str, str] = {
    "record_id": "ID",
    "title": "TI",
    "author_names": "AU",
    "author_affiliations": "AD",
    "journal": "T2",
    "conference_name": "T2",
    "volume": "VL",
    "issue": "IS",
    "pages": "SP",
    "abstract": "AB",
    "doi": "DO",
    "pmid": "AN",
    "issn": "SN",
    "isbn": "SN",
    "language": "LA",
    "publisher": "PB",
    "url": "UR",
    "notes": "N1",
}
NOTE_TAG = "N1"
KEYWORD_TAG = "KW"

RIS_TYPES = frozenset(
    """ABST ADVS AGGR ANCIENT ART BILL BLOG BOOK CASE CHAP CHART CLSWK COMP CONF
    CPAPER CTLG DATA DBASE DICT EBOOK ECHAP EDBOOK EJOUR ELEC ENCYC EQUA FIGURE GEN
    GOVDOC GRANT HEAR ICOMM INPR JFULL JOUR LEGAL MANSCPT MAP MGZN MPCT MULTI MUSIC
    NEWS PAMP PAT PCOMM RPRT SER SLIDE SOUND STAND STAT THES UNBILL UNPB
    VIDEO""".split()
)
TYPE_CODES: dict[str, str] = {
    "Journal article": "JOUR",
    "Review": "JOUR",
    "Book": "BOOK",
    "Book chapter": "CHAP",
    "Conference paper": "CONF",
    "Conference abstract": "ABST",
    "Thesis": "THES",
    "Report": "RPRT",
    "Dataset": "DATA",
    "Preprint": "UNPB",
    "Letter": "JOUR",
    "Editorial": "JOUR",
    "Note": "JOUR",
    "Erratum": "JOUR",
    "Retraction": "JOUR",
}
_GENERIC_TYPE = "GEN"


def ris_type(publication_type: str | None) -> str:
    """A stored RIS code passes through; anything else goes through Cleaning's
    aliases to a standard type, and from there to its code."""
    first = (publication_type or "").split(LINE_DELIMITER)[0].strip()
    if first in RIS_TYPES:
        return first
    standard = STANDARD_PUBLICATION_TYPE.get(first.lower(), first)
    return TYPE_CODES.get(standard, _GENERIC_TYPE)
