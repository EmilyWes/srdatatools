from dataclasses import dataclass
from functools import cached_property

from app.models.record import LabelValue


@dataclass(frozen=True)
class ParseSettings:
    # Lowercased value -> decision; overrides the built-in spellings.
    label_values: tuple[tuple[str, LabelValue], ...] = ()
    # Python's csv limit is process-wide, so the parser sets it before each parse.
    csv_field_size_limit: int = 1_000_000
    use_first: tuple[str, ...] = ()

    # Cached: the lookup runs for every label of every record.
    @cached_property
    def label_lookup(self) -> dict[str, LabelValue]:
        return dict(self.label_values)


NO_QUIRKS = ParseSettings()
