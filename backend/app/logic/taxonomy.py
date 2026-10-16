"""Category identity: "Milk", "milk" and "MILK" are one category.

A user's category list says which spelling is the real one. Anything saved under another
casing is corrected to it (see app.db.category_events), and creating a duplicate by hand
is refused with a message naming the existing one.
"""
from __future__ import annotations

import re
from collections import Counter

_SPACES = re.compile(r"\s+")


def clean_category(name) -> str:
    """The name trimmed, with inner whitespace collapsed; case is kept."""
    return _SPACES.sub(" ", str(name or "")).strip()


def category_key(name) -> str:
    """Identity of a category: case- and spacing-insensitive. Accents are kept."""
    return clean_category(name).casefold()


def find_existing(existing: list[str], name) -> str | None:
    """The spelling in `existing` that `name` is a case variant of (or equal to), if any."""
    cleaned = clean_category(name)
    if not cleaned:
        return None
    if cleaned in existing:
        return cleaned
    key = category_key(cleaned)
    return next((c for c in existing if category_key(c) == key), None)


class CategoryResolver:
    """Maps any spelling of a category to the one to store.

    Seeded with the user's category list. A category the list doesn't have yet is
    remembered as first seen, so later variants in the same batch (an import, say)
    follow it. When the list itself holds two variants, an exact match is left alone.
    """

    def __init__(self, existing: list[str] | None = None):
        self._exact = {c for c in (existing or [])}
        self._by_key: dict[str, str] = {}
        for c in existing or []:
            self._by_key.setdefault(category_key(c), clean_category(c))

    def resolve(self, name) -> str:
        cleaned = clean_category(name)
        if not cleaned or cleaned in self._exact:
            return cleaned
        return self._by_key.setdefault(category_key(cleaned), cleaned)


def preferred_spelling(variants: Counter, listed: list[str]) -> str:
    """Which spelling to keep when a user has several: a listed one, then the most used.

    Ties go to alphabetical order, which puts the capitalised form first ("Milk" < "milk").
    """
    pool = [v for v in variants if v in listed] or list(variants)
    return min(pool, key=lambda v: (-variants[v], v))
