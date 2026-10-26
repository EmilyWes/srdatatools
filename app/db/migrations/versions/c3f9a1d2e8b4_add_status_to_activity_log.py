"""add status to activity_log

Revision ID: c3f9a1d2e8b4
Revises: 5b1e8c4d7a2f
Create Date: 2026-10-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3f9a1d2e8b4"
down_revision: Union[str, Sequence[str], None] = "5b1e8c4d7a2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(), nullable=False, server_default="ok")
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.drop_column("status")
