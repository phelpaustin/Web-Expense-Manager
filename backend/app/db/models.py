from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, String, UniqueConstraint

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    description = Column(String, nullable=False, default="")
    amount = Column(Float, nullable=False)


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


