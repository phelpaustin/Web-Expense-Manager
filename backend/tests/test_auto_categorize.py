from app.logic.categorizer import auto_categorize_missing


def _e(i, category, shop="", description="", subcategory=""):
    return {"id": i, "category": category, "shop": shop, "description": description, "subcategory": subcategory}


def test_uses_the_most_common_category_and_subcategory_the_shop_had_before():
    rows = [
        _e(1, "Groceries", "ICA", subcategory="Dairy"),
        _e(2, "Groceries", "ica ", subcategory="Dairy"),
        _e(3, "Fun", "ICA"),
        _e(4, "", "ICA"),
    ]
    assert auto_categorize_missing(rows) == [(4, "Groceries", "Dairy")]


def test_falls_back_to_keyword_rules_and_skips_what_it_cannot_place():
    rows = [_e(1, "Uncategorized", description="pizza slice"), _e(2, "", description="zzz qqq")]
    result = auto_categorize_missing(rows)
    assert [r[0] for r in result] == [1]


def test_other_uncategorized_rows_are_not_treated_as_history():
    rows = [_e(1, "Uncategorized", "Kiosk"), _e(2, "Uncategorized", "Kiosk"), _e(3, "", "Kiosk", description="coffee")]
    assert all(cat != "Uncategorized" for _, cat, _ in auto_categorize_missing(rows))
