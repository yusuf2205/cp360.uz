"""phone sign-in and long-lived device sessions

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.alter_column("email", existing_type=sa.String(255), nullable=True)
        b.alter_column("password_hash", existing_type=sa.String(255), nullable=True)
        b.add_column(sa.Column("phone", sa.String(20), nullable=True))
        b.create_index("ix_users_phone", ["phone"], unique=True)
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("poll_secret", sa.String(64), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("device", sa.String(300)),
        sa.Column("ip", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_jti", "user_sessions", ["jti"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_sessions_jti", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    with op.batch_alter_table("users") as b:
        b.drop_index("ix_users_phone")
        b.drop_column("phone")
