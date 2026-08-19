"""Run Alembic migrations to head on startup."""
import os

from alembic import command
from alembic.config import Config

# backend/ directory (this file is backend/app/db/migrate.py).
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migrations() -> None:
    cfg = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))
    command.upgrade(cfg, "head")
