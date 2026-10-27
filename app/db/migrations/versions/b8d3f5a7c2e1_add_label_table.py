"""add label table

Revision ID: b8d3f5a7c2e1
Revises: a4c8e2f6b1d9
Create Date: 2026-10-27 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b8d3f5a7c2e1"
down_revision: Union[str, Sequence[str], None] = "a4c8e2f6b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "label",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("source_file_id", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("screener", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["record.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["source_file.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("label", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_label_record_id"), ["record_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_label_source_file_id"), ["source_file_id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("label", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_label_source_file_id"))
        batch_op.drop_index(batch_op.f("ix_label_record_id"))

    op.drop_table("label")
