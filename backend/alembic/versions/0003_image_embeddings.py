"""Add image_embedding column to posts

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-19
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column(
            "image_embedding",
            sa.ARRAY(sa.Float()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("posts", "image_embedding")
