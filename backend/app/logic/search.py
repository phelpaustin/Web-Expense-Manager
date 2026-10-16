"""Helpers for "contains" text search, shared by the expense and bill lists."""

LIKE_ESCAPE = "\\"


def like_pattern(text: str) -> str:
    """A `%text%` LIKE pattern in which the user's own % and _ are ordinary characters.

    Without this, searching for "100%" or "a_b" treats them as wildcards and matches far
    more than was typed. Use it with ``.ilike(pattern, escape=LIKE_ESCAPE)``; ILIKE already
    ignores case.
    """
    escaped = (
        text.strip()
        .replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"
