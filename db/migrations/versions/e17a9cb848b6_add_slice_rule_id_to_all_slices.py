"""add_slice_rule_id_to_all_slices

Revision ID: e17a9cb848b6
Revises: 0017
Create Date: 2026-03-18 20:40:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e17a9cb848b6"
down_revision = "0017"
branch_labels = None
depends_on = None

tables = [
    "fact_velocity_slices",
    "fact_throughput_slices",
    "fact_backlog_growth_slices",
    "fact_lead_time_slices",
    "fact_time_to_market_slices",
    "fact_flow_efficiency_slices",
    "fact_work_item_aging_slices",
]


def upgrade() -> None:
    for table in tables:
        # 1. Add column
        op.add_column(
            table,
            sa.Column("slice_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
            schema="metrics",
        )

        # 2. Add foreign key
        op.create_foreign_key(
            f"fk_{table}_slice_rule_id",
            table,
            "metric_slice_rules",
            ["slice_rule_id"],
            ["id"],
            source_schema="metrics",
            referent_schema="metrics",
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table in tables:
        # 1. Drop foreign key
        op.drop_constraint(
            f"fk_{table}_slice_rule_id", table, schema="metrics", type_="foreignkey"
        )

        # 2. Drop column
        op.drop_column(table, "slice_rule_id", schema="metrics")
