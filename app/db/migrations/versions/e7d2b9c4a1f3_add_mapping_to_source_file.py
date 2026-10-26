"""add mapping to source_file

Revision ID: e7d2b9c4a1f3
Revises: c3f9a1d2e8b4
Create Date: 2026-10-26 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e7d2b9c4a1f3"
down_revision: Union[str, Sequence[str], None] = "c3f9a1d2e8b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("field_mapping", "suggested_mapping", "file_summary")


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("source_file", schema=None) as batch_op:
        for name in _COLUMNS:
            batch_op.add_column(
                sa.Column(name, sa.JSON(), nullable=False, server_default="{}")
            )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("source_file", schema=None) as batch_op:
        for name in reversed(_COLUMNS):
            batch_op.drop_column(name)
