"""add sheet to source_file

Revision ID: a4c8e2f6b1d9
Revises: e7d2b9c4a1f3
Create Date: 2026-10-27 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a4c8e2f6b1d9"
down_revision: Union[str, Sequence[str], None] = "e7d2b9c4a1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("source_file", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sheet", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("source_file", schema=None) as batch_op:
        batch_op.drop_column("sheet")
