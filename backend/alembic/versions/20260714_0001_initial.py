"""Initialize the database migration history.

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""

from collections.abc import Sequence

revision: str = "20260714_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the initial empty schema baseline."""


def downgrade() -> None:
    """Return to a database without MyCRM migrations."""
