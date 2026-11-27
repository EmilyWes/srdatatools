from app.helpers.record_fields import FIELD_LABELS
from app.models.record import Record


def test_field_labels__cover_every_record_field() -> None:
    # Author IDs and labels are shown as one column per key or pair instead.
    assert set(FIELD_LABELS) == set(Record.model_fields) - {"author_ids", "labels"}
