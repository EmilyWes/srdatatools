from app.parsers.profiles.base import FormatProfile, Profile, apply_profile, fix_record
from app.parsers.profiles.default import DEFAULT_PROFILES
from app.parsers.profiles.openalex import OPENALEX
from app.parsers.profiles.pubmed import PUBMED
from app.parsers.profiles.scopus import SCOPUS

__all__ = [
    "PROFILES",
    "FormatProfile",
    "Profile",
    "apply_profile",
    "fix_record",
    "has_profile",
    "profile_for",
]

PROFILES: dict[str, Profile] = {
    profile.key: profile for profile in (PUBMED, SCOPUS, OPENALEX)
}


def has_profile(source: str, file_type: str) -> bool:
    profile = PROFILES.get(source)
    return profile is not None and file_type in profile.formats


def profile_for(source: str, file_type: str) -> FormatProfile | None:
    """The source's profile for the Type, else the Type's default profile."""
    profile = PROFILES.get(source)
    if profile is not None and file_type in profile.formats:
        return profile.formats[file_type]
    return DEFAULT_PROFILES.get(file_type)
