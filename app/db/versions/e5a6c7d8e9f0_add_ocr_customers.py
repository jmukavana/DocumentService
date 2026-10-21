"""Add customer API credentials and monthly OCR usage.

Revision ID: e5a6c7d8e9f0
Revises: d4e5f6a7b8c9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a6c7d8e9f0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("monthly_request_limit", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("monthly_request_limit >= 0", name="ck_customer_limit_nonnegative"),
    )
    op.create_table(
        "customer_api_keys",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_customer_api_keys_customer_id", "customer_api_keys", ["customer_id"])
    op.create_table(
        "ocr_usage",
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("customer_id", "period"),
        sa.CheckConstraint("requests >= 0", name="ck_ocr_usage_nonnegative"),
    )


def downgrade() -> None:
    op.drop_table("ocr_usage")
    op.drop_index("ix_customer_api_keys_customer_id", table_name="customer_api_keys")
    op.drop_table("customer_api_keys")
    op.drop_table("customers")
