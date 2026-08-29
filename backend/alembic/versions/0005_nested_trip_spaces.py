"""Nested Expense Spaces + trips-as-spaces merge (idempotent).

Adds parent/trip fields to groups, per-member local mapping fields to
group_members, and copies any legacy `trips` rows into `groups` with
space_type='trip' (repointing expenses.group_id along the way). The legacy
`trips` table is left untouched as a historical copy.

Revision ID: 0005_nested_trip_spaces
Revises: 0004_space_type
Create Date: 2026-08-29
"""
import sqlalchemy as sa

from alembic import op

revision = "0005_nested_trip_spaces"
down_revision = "0004_space_type"
branch_labels = None
depends_on = None


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    group_additions = [
        ("parent_group_id", sa.Integer(), None),
        ("destination", sa.String(), None),
        ("start_date", sa.Date(), None),
        ("end_date", sa.Date(), None),
        ("budget", sa.Float(), None),
        ("currency", sa.String(), "'SEK'"),
        ("status", sa.String(), "'Planned'"),
        ("migrated_from_trip_id", sa.Integer(), None),
    ]
    for col, coltype, default in group_additions:
        if insp.has_table("groups") and col not in _columns(insp, "groups"):
            kwargs = {"nullable": True}
            if default is not None:
                kwargs["server_default"] = sa.text(default)
            op.add_column("groups", sa.Column(col, coltype, **kwargs))

    member_additions = [("local_name", sa.String(), None), ("local_parent_group_id", sa.Integer(), None)]
    for col, coltype, _default in member_additions:
        if insp.has_table("group_members") and col not in _columns(insp, "group_members"):
            op.add_column("group_members", sa.Column(col, coltype, nullable=True))

    # Re-inspect: the columns above must exist before the data copy below can use them.
    insp = sa.inspect(bind)
    if not insp.has_table("trips"):
        return

    legacy_trips = bind.execute(
        sa.text(
            "SELECT id, user_id, name, destination, start_date, end_date, budget, currency, status FROM trips"
        )
    ).fetchall()

    for t in legacy_trips:
        existing = bind.execute(
            sa.text("SELECT id FROM groups WHERE migrated_from_trip_id = :tid"), {"tid": t.id}
        ).fetchone()
        if existing:
            new_group_id = existing.id
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO groups (owner_id, name, space_type, destination, start_date, end_date, "
                    "budget, currency, status, migrated_from_trip_id) "
                    "VALUES (:owner_id, :name, 'trip', :destination, :start_date, :end_date, "
                    ":budget, :currency, :status, :tid)"
                ),
                {
                    "owner_id": t.user_id,
                    "name": t.name,
                    "destination": t.destination,
                    "start_date": t.start_date,
                    "end_date": t.end_date,
                    "budget": t.budget,
                    "currency": t.currency,
                    "status": t.status,
                    "tid": t.id,
                },
            )
            new_group_id = bind.execute(
                sa.text("SELECT id FROM groups WHERE migrated_from_trip_id = :tid"), {"tid": t.id}
            ).fetchone().id
            bind.execute(
                sa.text("INSERT INTO group_members (group_id, user_id, role) VALUES (:gid, :uid, 'owner')"),
                {"gid": new_group_id, "uid": t.user_id},
            )

        if insp.has_table("expenses") and "trip_id" in _columns(insp, "expenses"):
            bind.execute(
                sa.text("UPDATE expenses SET group_id = :gid WHERE trip_id = :tid"),
                {"gid": new_group_id, "tid": t.id},
            )


def downgrade():
    pass
