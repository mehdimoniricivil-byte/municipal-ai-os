"""v0.5 baseline for existing installations.

New installations create the current schema from SQLAlchemy metadata. Existing
v0.4 databases should be stamped after taking a backup because their tables
already exist: ``alembic stamp 0001_v050``.
"""
from alembic import op
from app.db.base import Base
import app.db.models  # noqa: F401

revision = "0001_v050"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
