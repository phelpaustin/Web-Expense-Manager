from sqlalchemy import engine_from_config, pool

from alembic import context

from app.core.config import settings
from app.db.database import Base
from app.db import models  # noqa: F401 — imported so all tables register on Base.metadata

config = context.config

# Use the app's database URL (normalizing the postgres:// scheme like the app does).
_url = settings.database_url
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)
config.set_main_option("sqlalchemy.url", _url)

target_metadata = Base.metadata


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
