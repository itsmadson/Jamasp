"""reports become background jobs with multiple panels

Building a report is several model calls, so it moved off the request path. The
report row now carries the job's lifecycle.

Revision ID: a1b2c3d4e5f6
Revises: 6e1aefd648d7
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "6e1aefd648d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("question", sa.Text(), nullable=True))
    op.add_column(
        "reports",
        sa.Column(
            "status",
            sa.Enum(
                "queued", "running", "succeeded", "partial", "failed",
                name="report_status", native_enum=False,
            ),
            nullable=False,
            # SQLAlchemy's Enum persists member NAMES, so the default must be the
            # name. Seeding the lowercase value instead makes every existing report
            # unreadable the moment the model tries to resolve it.
            server_default="SUCCEEDED",
        ),
    )
    op.add_column("reports", sa.Column("error", sa.Text(), nullable=True))
    op.create_index(op.f("ix_reports_status"), "reports", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_status"), table_name="reports")
    op.drop_column("reports", "error")
    op.drop_column("reports", "status")
    op.drop_column("reports", "question")
