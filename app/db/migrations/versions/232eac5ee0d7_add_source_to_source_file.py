"""add source to source_file

Revision ID: 232eac5ee0d7
Revises: 90aaa46986e6
Create Date: 2026-10-16 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "232eac5ee0d7"
down_revision: Union[str, Sequence[str], None] = "90aaa46986e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("source_file", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("source_file", schema=None) as batch_op:
        batch_op.drop_column("source")
