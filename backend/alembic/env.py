from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  (register tables)
from app.config import settings
from app.db import Base

target_metadata = Base.metadata


def run_migrations_online():
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
