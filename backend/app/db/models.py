from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, JSON, LargeBinary, String, UniqueConstraint

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False, default="")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    subcategory = Column(String, nullable=False, default="")
    description = Column(String, nullable=False, default="")
    amount = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False, default=1.0)
    unit = Column(String, nullable=False, default="Count")
    shop = Column(String, nullable=False, default="")
    brand = Column(String, nullable=False, default="")
    currency = Column(String, nullable=False, default="SEK")
    price_per_unit = Column(Float, nullable=False, default=0.0)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True)


class UserOptions(Base):
    __tablename__ = "user_options"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    categories = Column(JSON, nullable=False, default=list)
    subcategories = Column(JSON, nullable=False, default=dict)  # {category: [subcategory, ...]}
    units = Column(JSON, nullable=False, default=list)
    shops = Column(JSON, nullable=False, default=list)
    base_currency = Column(String, nullable=False, default="SEK")
    budget_period = Column(String, nullable=False, default="Monthly")
    budget_rollover = Column(Boolean, nullable=False, default=False)



class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Category name; the overall budget uses the "__total_monthly__" sentinel.
    category = Column(String, nullable=False)
    amount = Column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_user_category"),)


class Income(Base):
    __tablename__ = "income"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    source = Column(String, nullable=False, default="Income")
    note = Column(String, nullable=False, default="")


class RecurringTemplate(Base):
    __tablename__ = "recurring_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item = Column(String, nullable=False)
    category = Column(String, nullable=False, default="")
    amount = Column(Float, nullable=False)
    frequency = Column(String, nullable=False, default="Monthly")
    note = Column(String, nullable=False, default="")
    auto_post = Column(Boolean, nullable=False, default=False)
    last_applied = Column(Date, nullable=True)


class PendingBill(Base):
    __tablename__ = "pending_bills"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    shop = Column(String, nullable=False, default="")
    amount = Column(Float, nullable=False)
    note = Column(String, nullable=False, default="")
    # "pending" until itemised into a real expense.
    status = Column(String, nullable=False, default="pending")


class ManualBill(Base):
    __tablename__ = "manual_bills"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    shop = Column(String, nullable=False, default="")
    amount = Column(Float, nullable=False)
    note = Column(String, nullable=False, default="")


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pending_bill_id = Column(Integer, ForeignKey("pending_bills.id"), nullable=False, index=True)
    filename = Column(String, nullable=False, default="receipt")
    content_type = Column(String, nullable=False, default="application/octet-stream")
    data = Column(LargeBinary, nullable=False)


class Trip(Base):
    """Legacy standalone trips table — superseded by Group(space_type='trip').
    Left unmapped-from going forward; existing rows are migrated into groups by
    the 0005 migration and this table is kept only as an untouched historical copy.
    """
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    destination = Column(String, nullable=False, default="")
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    budget = Column(Float, nullable=True)
    currency = Column(String, nullable=False, default="SEK")
    status = Column(String, nullable=False, default="Planned")


class Group(Base):
    """An Expense Space: a shared expense-tracking space (household, business, trip, ...).

    A Group with space_type='trip' is a Trip: it can optionally sit under a
    parent_group_id (e.g. a "Goa Trip" filed under "Household") and carries a
    few trip-only fields (destination/dates/budget/currency/status). Trip
    membership is independent of the parent space's membership — inviting
    someone to a trip never exposes the parent space's other data.
    """
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    # personal | household | business | rental | trip | custom
    space_type = Column(String, nullable=False, default="custom")
    parent_group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True)
    # Trip-only fields (unused for other space types):
    destination = Column(String, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    budget = Column(Float, nullable=True)
    currency = Column(String, nullable=True, default="SEK")
    status = Column(String, nullable=True, default="Planned")
    # Set only on rows created by the legacy-trips data migration, to make it idempotent.
    migrated_from_trip_id = Column(Integer, nullable=True, index=True)


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False, default="editor")  # "owner" | "admin" | "editor" | "viewer"
    # Per-member preference: how *this* member organises a shared space on their
    # own side (e.g. filing a shared trip under their own "Business" space, or
    # calling it something different locally). Purely organisational — it never
    # affects the underlying shared space or other members' views.
    local_name = Column(String, nullable=True)
    local_parent_group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)

    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_user"),)


class GroupInvite(Base):
    """A pending invite for an email that hasn't registered yet; claimed on signup."""
    __tablename__ = "group_invites"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False, default="editor")



