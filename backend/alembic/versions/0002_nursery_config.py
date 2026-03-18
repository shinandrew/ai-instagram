"""add nursery config columns to agents

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("nursery_enabled", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("agents", sa.Column("nursery_persona", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("nursery_style", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "nursery_style")
    op.drop_column("agents", "nursery_persona")
    op.drop_column("agents", "nursery_enabled")
