"""create books table

Revision ID: 0001_create_books
Revises:
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_create_books"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=False),
        sa.Column("genre", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("title", "author", name="uq_book_title_author"),
    )
    op.create_index(op.f("ix_books_id"), "books", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_books_id"), table_name="books")
    op.drop_table("books")
