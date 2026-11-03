from collections.abc import Mapping

from app.parsers.mapping import FieldMapping, RowDefaults, Suggest, make_row

_DEFAULTS = RowDefaults()


def mapping_of(
    rows: Mapping[str, str | Suggest], defaults: RowDefaults = _DEFAULTS
) -> FieldMapping:
    """Rows given as a target name use that target's default options."""
    return FieldMapping(
        rows={
            key: make_row(Suggest(row) if isinstance(row, str) else row, key, defaults)
            for key, row in rows.items()
        }
    )


def targets_of(mapping: FieldMapping) -> dict[str, str]:
    return {key: row.target for key, row in mapping.rows.items()}
