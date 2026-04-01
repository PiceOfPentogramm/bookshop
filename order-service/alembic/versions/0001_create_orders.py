"""create orders table

Revision ID: 0001_create_orders
Revises:
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_create_orders"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("total_price", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "confirmed", "delivered", "cancelled", name="orderstatus"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_orders_id"), "orders", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_id"), table_name="orders")
    op.drop_table("orders")
    op.execute("DROP TYPE IF EXISTS orderstatus")
