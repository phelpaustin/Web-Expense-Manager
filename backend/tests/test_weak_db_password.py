import pytest

from app.core.config import weak_db_password_reason


@pytest.mark.parametrize("url", [
    "postgresql://expense:PASSWORD@db:5432/expense",
    "postgresql://expense:change-me@db:5432/expense",
    "postgresql://expense:short1@db:5432/expense",
    "postgresql://expense@db:5432/expense",
])
def test_weak_passwords_are_reported(url):
    assert weak_db_password_reason(url)


@pytest.mark.parametrize("url", [
    "sqlite:///./expense.db",
    "postgresql://expense:3f9a1c0b7d2e4a68b5c1d9e0f2a4@db:5432/expense",
])
def test_strong_or_sqlite_is_fine(url):
    assert weak_db_password_reason(url) is None
