from collections.abc import Iterable, Sequence


def sniff_separator(
    values: Iterable[str | None], candidates: Sequence[str]
) -> str | None:
    """The candidate found in the most values; earlier candidates win ties."""
    counts = dict.fromkeys(candidates, 0)
    for value in values:
        for candidate in candidates:
            if value and candidate in value:
                counts[candidate] += 1
    best = max(counts, key=lambda candidate: counts[candidate])
    return best if counts[best] else None
