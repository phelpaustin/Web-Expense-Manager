"""Item and shop name merges: the user's own "these are the same thing" rules.

Rules are applied when the price tracker analyses data (see app.logic.names); no expense
is ever rewritten, so removing a rule restores the original grouping.
"""
from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.expenses import fetch_expenses
from app.db import models
from app.db.database import get_db
from app.logic import names

router = APIRouter()

Kind = Literal["item", "shop"]
MAX_ALIASES_PER_KIND = 2000
MAX_NAME_LENGTH = 200


class MergeIn(BaseModel):
    kind: Kind
    names: list[str] = Field(min_length=1, max_length=50)
    canonical: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)

    @field_validator("canonical")
    @classmethod
    def _canonical_not_blank(cls, v: str) -> str:
        cleaned = names.clean_name(v)
        if not cleaned:
            raise ValueError("canonical name must not be blank")
        return cleaned

    @field_validator("names")
    @classmethod
    def _names_valid(cls, v: list[str]) -> list[str]:
        cleaned = [names.clean_name(n) for n in v]
        if any(len(n) > MAX_NAME_LENGTH for n in cleaned):
            raise ValueError(f"names must be at most {MAX_NAME_LENGTH} characters")
        return [n for n in cleaned if n]


def _out(row: models.NameAlias) -> dict:
    return {"id": row.id, "kind": row.kind, "alias": row.alias, "canonical": row.canonical}


def alias_map(db: Session, user_id: int, kind: str) -> dict[str, str]:
    """name key -> canonical name, for one kind of name."""
    rows = db.query(models.NameAlias).filter(models.NameAlias.user_id == user_id, models.NameAlias.kind == kind).all()
    return {r.alias_key: r.canonical for r in rows}


def load_alias_maps(db: Session, user_id: int) -> tuple[dict[str, str], dict[str, str]]:
    """(item aliases, shop aliases), ready for names.canonicalise()."""
    return alias_map(db, user_id, "item"), alias_map(db, user_id, "shop")


@router.get("/aliases")
def list_aliases(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = (
        db.query(models.NameAlias)
        .filter(models.NameAlias.user_id == user.id)
        .order_by(models.NameAlias.canonical, models.NameAlias.alias)
        .all()
    )
    return {
        "items": [_out(r) for r in rows if r.kind == "item"],
        "shops": [_out(r) for r in rows if r.kind == "shop"],
    }


@router.post("/aliases/merge")
def merge_names(payload: MergeIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Treat every name in `names` as `canonical`.

    Rules never chain, so a merge keeps that true: if `canonical` is itself an alias it
    resolves to its own target first, and rules that pointed at a name being merged
    away are re-pointed at the new target.
    """
    existing = {
        r.alias_key: r
        for r in db.query(models.NameAlias).filter(
            models.NameAlias.user_id == user.id, models.NameAlias.kind == payload.kind
        )
    }
    target = payload.canonical
    if names.name_key(target) in existing:
        target = existing[names.name_key(target)].canonical
    target_key = names.name_key(target)

    sources = {}
    for name in payload.names:
        key = names.name_key(name)
        if key and key != target_key:
            sources.setdefault(key, name)
    if not sources:
        raise HTTPException(status_code=400, detail="Choose at least one name that differs from the one to keep.")
    if len(existing) + len([k for k in sources if k not in existing]) > MAX_ALIASES_PER_KIND:
        raise HTTPException(status_code=400, detail="Too many merges saved; remove some first.")

    for key, name in sources.items():
        row = existing.get(key)
        if row is None:
            db.add(models.NameAlias(user_id=user.id, kind=payload.kind, alias=name, alias_key=key, canonical=target))
        else:
            row.canonical = target
    for row in existing.values():  # rules that pointed at a name now merged away
        if names.name_key(row.canonical) in sources:
            row.canonical = target
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Those names changed while saving; please try again.")
    return {"canonical": target, "merged": len(sources)}


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(alias_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.get(models.NameAlias, alias_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Merge not found")
    db.delete(row)
    db.commit()


@router.get("/aliases/suggestions")
def suggestions(kind: Kind, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Groups of item (or shop) names that look like the same thing and aren't merged yet."""
    item_aliases, shop_aliases = load_alias_maps(db, user.id)
    rows = names.canonicalise(fetch_expenses(db, user.id), item_aliases, shop_aliases)
    field = "description" if kind == "item" else "shop"
    # A recorded bill total's description is just its shop's name: not an item.
    counts = Counter(r[field] for r in rows if r[field] and not (kind == "item" and r["bill_total_only"]))
    return {"groups": names.suggest_merges(list(counts.items()))}
