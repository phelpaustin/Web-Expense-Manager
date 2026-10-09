"""Shared request-validation helpers."""
from typing import Any, ClassVar

from pydantic import BaseModel, field_validator


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
