"""Guards on the migration chain that SQLite can't enforce but Postgres (production) does.

Alembic records the current revision in alembic_version.version_num, a VARCHAR(32). SQLite
ignores that width, so a longer revision id sails through every test here and then fails
the real deploy with "value too long for type character varying(32)", after the migration
body has already run and been rolled back.
"""
import os

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_NUM_WIDTH = 32  # alembic's own column width for alembic_version.version_num


def _script() -> ScriptDirectory:
    cfg = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_every_revision_id_fits_the_alembic_version_column():
    too_long = {r.revision: len(r.revision) for r in _script().walk_revisions() if len(r.revision) > VERSION_NUM_WIDTH}

    assert too_long == {}, (
        f"Revision ids must be at most {VERSION_NUM_WIDTH} characters (alembic_version.version_num is "
        f"VARCHAR({VERSION_NUM_WIDTH}); Postgres rejects longer ids, SQLite does not). Shorten: {too_long}"
    )


def test_the_history_is_one_straight_line_with_a_single_head():
    script = _script()
    revisions = list(script.walk_revisions())

    assert len(script.get_heads()) == 1, f"several migration heads: {script.get_heads()}"
    assert all(not isinstance(r.down_revision, tuple) for r in revisions), "a migration merges two branches"
    assert len({r.revision for r in revisions}) == len(revisions)


def test_each_migration_file_is_named_after_its_revision_id():
    mismatched = {os.path.basename(r.path)[:-3]: r.revision for r in _script().walk_revisions()
                  if os.path.basename(r.path)[:-3] != r.revision}

    assert mismatched == {}
