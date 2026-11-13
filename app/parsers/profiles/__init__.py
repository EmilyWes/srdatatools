from collections.abc import Collection
from dataclasses import fields, replace

from app.parsers.common import FileType
from app.parsers.profiles.asreview import ASREVIEW
from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import DEFAULT_PROFILES
from app.parsers.profiles.openalex import OPENALEX
from app.parsers.profiles.pubmed import PUBMED
from app.parsers.profiles.scopus import SCOPUS
from app.parsers.quirks import ParseSettings

__all__ = [
    "PROFILES",
    "FormatProfile",
    "Profile",
    "profile_for",
]

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
