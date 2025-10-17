"""Initial empty revision (baseline).

Revision ID: 0001_initial
Revises: None
Create Date: 2025-10-17
"""

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Baseline migration: no-op because initial schemas are created by db/init scripts.
    Use Alembic for subsequent schema changes."""
    pass


def downgrade() -> None:
    # no-op
    pass
