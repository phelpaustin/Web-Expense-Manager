"""Item and shop name identity: treat spelling variants as one thing, without editing data.

Free-text names make the same product look like several ("Milk", "milk ", "Milk 1L").
Two layers fix that at analysis time, leaving every stored expense untouched:

  1. A name key (case, spacing and trailing punctuation ignored) merges trivial variants
     automatically.
  2. The user's own aliases ("Milk 1L" -> "Milk") merge the rest, and are reversible.

suggest_merges() proposes aliases the user might want, from the names actually in use.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher

_SPACES = re.compile(r"\s+")
_EDGE_PUNCT = " .,;:"


def clean_name(value) -> str:
    """The name as shown: trimmed with inner whitespace collapsed (case is kept)."""
    return _SPACES.sub(" ", str(value or "")).strip()


def name_key(value) -> str:
    """The identity of a name: case-insensitive, whitespace- and edge-punctuation-insensitive.

    Accents are deliberately kept: in Swedish, a/å/ä and o/ö are different letters.
    """
    return clean_name(value).casefold().strip(_EDGE_PUNCT)


def resolve_name(name, aliases: dict[str, str]) -> str:
    """The canonical name for `name`, or the name itself when it has no alias."""
    cleaned = clean_name(name)
    return aliases.get(name_key(cleaned), cleaned)


def canonicalise(expenses: list[dict], item_aliases: dict[str, str], shop_aliases: dict[str, str]) -> list[dict]:
    """Copies of the expenses with `description` and `shop` replaced by their canonical names.

    `*_aliases` map a name key to the canonical name it should become. Names that share
    a key after aliasing are one name; it is shown as the alias target if there is one,
    otherwise as the spelling used most often (ties go to alphabetical order).
    """
    item_names = _canonical_names([e.get("description") for e in expenses], item_aliases)
    shop_names = _canonical_names([e.get("shop") for e in expenses], shop_aliases)
    out = []
    for e in expenses:
        row = dict(e)
        row["description"] = item_names.get(name_key(e.get("description")), clean_name(e.get("description")))
        row["shop"] = shop_names.get(name_key(e.get("shop")), clean_name(e.get("shop")))
        out.append(row)
    return out


def _canonical_names(raw_names: list, aliases: dict[str, str]) -> dict[str, str]:
    """name key -> the name to show for it, with aliases already applied."""
    target_text = {name_key(text): clean_name(text) for text in aliases.values()}
    spellings: dict[str, Counter] = defaultdict(Counter)
    for raw in raw_names:
        if not clean_name(raw):
            continue
        spellings[name_key(raw)][clean_name(raw)] += 1

    shown: dict[str, str] = {}
    groups: dict[str, Counter] = defaultdict(Counter)  # effective key -> spellings seen
    for key, counts in spellings.items():
        effective = name_key(aliases[key]) if key in aliases else key
        groups[effective].update(counts)
        shown[key] = effective
    best = {
        eff: target_text.get(eff) or min(counts, key=lambda s: (-counts[s], s))
        for eff, counts in groups.items()
    }
    return {key: best[eff] for key, eff in shown.items()}


# --- suggestions -----------------------------------------------------------------------

_SIZE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|mg|l|ml|cl|dl|st|pcs|pc|pack|oz|lb)\b", re.IGNORECASE)
_MAX_NAMES = 600  # distinct names compared; the most-used ones, so the cost stays bounded
_SIMILARITY = 0.88


def _match_key(name: str) -> str:
    """A name with any size/weight removed ("Milk 1.5 L" -> "milk"), for matching only."""
    return _SPACES.sub(" ", _SIZE.sub(" ", name_key(name))).strip(_EDGE_PUNCT + "-")


def _same_but_plural(a: str, b: str) -> bool:
    short, long = sorted((a, b), key=len)
    return len(short) >= 3 and (long == short + "s" or long == short + "es")


def _close(a: str, b: str) -> bool:
    if a == b or _same_but_plural(a, b):
        return True
    if len(a) < 5 or len(b) < 5 or a[0] != b[0] or abs(len(a) - len(b)) > 2:
        return False  # short names differ by one letter and are still different things
    matcher = SequenceMatcher(None, a, b)
    return matcher.real_quick_ratio() >= _SIMILARITY and matcher.quick_ratio() >= _SIMILARITY and matcher.ratio() >= _SIMILARITY


def suggest_merges(names: list[tuple[str, int]], limit: int = 50) -> list[dict]:
    """Groups of names in use that probably mean the same thing, most-used first.

    `names` are (name, times used) pairs, ideally already canonicalised so merges made
    before aren't offered again. Each group lists its members and the name to keep
    (the most used; the shortest on a tie). `reason` is "size" when the names differ
    only by a quantity ("Milk 1L"), otherwise "similar" (spelling or plural).
    """
    ranked = sorted(((clean_name(n), c) for n, c in names if clean_name(n)), key=lambda p: (-p[1], p[0]))[:_MAX_NAMES]
    keys = [_match_key(n) or name_key(n) for n, _ in ranked]
    parent = list(range(len(ranked)))
    via_similarity: set[int] = set()

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int, similar: bool) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri
        if similar:
            via_similarity.update((i, j))

    by_initial: dict[str, list[int]] = defaultdict(list)
    for i, key in enumerate(keys):
        for j in by_initial[key[:1]]:
            if keys[j] == key:
                union(i, j, similar=False)  # identical once the size is ignored
            elif _close(keys[i], keys[j]):
                union(i, j, similar=True)
        by_initial[key[:1]].append(i)

    members: dict[int, list[int]] = defaultdict(list)
    for i in range(len(ranked)):
        members[find(i)].append(i)

    groups = []
    for idxs in members.values():
        if len(idxs) < 2:
            continue
        chosen = max(idxs, key=lambda i: (ranked[i][1], -len(ranked[i][0]), ranked[i][0]))
        groups.append({
            "names": [{"name": ranked[i][0], "count": ranked[i][1]} for i in sorted(idxs, key=lambda i: (-ranked[i][1], ranked[i][0]))],
            "suggested": ranked[chosen][0],
            "reason": "similar" if any(i in via_similarity for i in idxs) else "size",
            "total": sum(ranked[i][1] for i in idxs),
        })
    groups.sort(key=lambda g: (-g["total"], g["suggested"]))
    return groups[:limit]
