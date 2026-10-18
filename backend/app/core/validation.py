"""Shared request-validation helpers."""
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, StringConstraints, field_validator

# Names people type: surrounding spaces are removed and the result must not be empty,
# so "   " is rejected (422) instead of being saved as a blank category or shop.
MAX_NAME = 200
MAX_TEXT = 1000
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME)]
# The same, but the field may be empty (subcategory, shop, brand, unit ...).
OptionalName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_NAME)]
# Free text (descriptions, notes), capped so a single row cannot be megabytes.
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_TEXT)]


class PartialUpdate(BaseModel):
    """Base for PUT bodies where an omitted field means "leave unchanged".

    Fields named in ``not_nullable`` may be left out but must never be sent as an
    explicit ``null``: they map to NOT NULL columns, so a null would otherwise
    reach the database and surface as a 500. It is rejected as a normal 422
    naming the field instead. Fields not listed (e.g. ``group_id``, where null
    means "move to personal") accept null.
    """

    not_nullable: ClassVar[frozenset[str]] = frozenset()

    @field_validator("*", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: Any, info) -> Any:
        if value is None and info.field_name in cls.not_nullable:
            raise ValueError("cannot be null")
        return value
