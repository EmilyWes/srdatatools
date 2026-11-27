from collections.abc import Collection
from dataclasses import fields, replace

from app.gui.importing.common import FileType
from app.gui.importing.parse_settings import ParseSettings
from app.gui.importing.profiles.asreview import ASREVIEW
from app.gui.importing.profiles.base import FormatProfile, Profile
from app.gui.importing.profiles.default import DEFAULT_PROFILES
from app.gui.importing.profiles.openalex import OPENALEX
from app.gui.importing.profiles.pubmed import PUBMED
from app.gui.importing.profiles.scopus import SCOPUS

__all__ = [
    "PROFILES",
    "FormatProfile",
    "Profile",
    "profile_for",
    "source_label",
    "sources_label",
]

_UNKNOWN_SOURCE = "Unknown"

# Detected profiles are applied in this order, each on top of the one before.
# ASReview last: it writes a vendor export back with its own columns added.
PROFILES: dict[str, Profile] = {
    profile.key: profile for profile in (PUBMED, SCOPUS, OPENALEX, ASREVIEW)
}


def _layer(
    base: FormatProfile, top: FormatProfile, defaults: ParseSettings
) -> FormatProfile:
    """Top's aliases win; a key it suggests is no longer ignored; only the settings
    it changes from the Type's default override base's."""
    changed = {
        f.name: getattr(top.settings, f.name)
        for f in fields(top.settings)
        if getattr(top.settings, f.name) != getattr(defaults, f.name)
    }
    return replace(
        base,
        suggestions={**base.suggestions, **top.suggestions},
        ignored_keys=(base.ignored_keys - top.suggestions.keys()) | top.ignored_keys,
        settings=replace(base.settings, **changed),
    )


def profile_for(sources: Collection[str], file_type: FileType) -> FormatProfile | None:
    """The Type's default profile with each source's profile for the Type layered
    on in PROFILES order."""
    default = DEFAULT_PROFILES.get(file_type)
    if default is None:
        return None
    profile = default
    for key, source_profile in PROFILES.items():
        top = source_profile.formats.get(file_type)
        if key in sources and top is not None:
            profile = _layer(profile, top, default.settings)
    return profile


def source_label(source: str | None) -> str:
    if source is None:
        return _UNKNOWN_SOURCE
    profile = PROFILES.get(source)
    return profile.label if profile is not None else source


def sources_label(sources: Collection[str]) -> str:
    return ", ".join(map(source_label, sources)) or _UNKNOWN_SOURCE
