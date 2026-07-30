"""normalize report status to enum member names

The previous revision seeded the lowercase enum value, but SQLAlchemy persists
member names, so any row created by it fails to load.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE reports SET status = upper(status) WHERE status <> upper(status)")


def downgrade() -> None:
    # Lowercasing again would only restore the unreadable state.
    pass
