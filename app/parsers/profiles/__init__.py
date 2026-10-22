from app.parsers.profiles.base import FormatProfile, Profile, apply_profile
from app.parsers.profiles.pubmed import PUBMED
from app.parsers.profiles.scopus import SCOPUS

__all__ = ["PROFILES", "FormatProfile", "Profile", "apply_profile", "profile_for"]

PROFILES: dict[str, Profile] = {profile.key: profile for profile in (PUBMED, SCOPUS)}


def profile_for(source: str, file_format: str) -> FormatProfile | None:
    profile = PROFILES.get(source)
    return profile.formats.get(file_format) if profile is not None else None
