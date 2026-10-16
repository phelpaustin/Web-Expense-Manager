from app.logic import names


def rows(*pairs):
    return [{"description": d, "shop": s} for d, s in pairs]


def test_name_key_ignores_case_spacing_and_edge_punctuation_but_keeps_accents():
    assert names.name_key("  Milk ") == names.name_key("MILK") == names.name_key("milk.") == "milk"
    assert names.name_key("Whole   milk") == names.name_key("whole milk")
    # Swedish letters are distinct: far (father) is not får (sheep).
    assert names.name_key("får") != names.name_key("far")


def test_variants_with_one_key_share_the_most_used_spelling():
    out = names.canonicalise(rows(("milk", "ica"), ("Milk", "ICA"), ("Milk", "Ica"), ("MILK ", "ICA")), {}, {})
    assert {r["description"] for r in out} == {"Milk"}  # used twice; "milk" and "MILK" once each
    assert {r["shop"] for r in out} == {"ICA"}  # used twice; "ica" and "Ica" once each


def test_the_spelling_tie_break_is_stable():
    out = names.canonicalise(rows(("b milk", ""), ("B Milk", "")), {}, {})
    assert len({r["description"] for r in out}) == 1
    assert out[0]["description"] == "B Milk"  # alphabetical when equally used


def test_an_alias_replaces_the_name_and_its_target_text_is_what_is_shown():
    aliases = {"milk 1l": "Whole milk"}
    out = names.canonicalise(rows(("Milk 1L", ""), ("whole milk", ""), ("Whole milk", "")), aliases, {})
    assert [r["description"] for r in out] == ["Whole milk"] * 3


def test_blank_names_stay_blank_and_inputs_are_not_modified():
    original = rows(("  ", None), ("Tea", ""))
    out = names.canonicalise(original, {}, {})
    assert out[0]["description"] == "" and out[0]["shop"] == ""
    assert original[0]["description"] == "  "  # the caller's rows are untouched


def test_resolve_name():
    aliases = {"milk 1l": "Milk"}
    assert names.resolve_name("  MILK 1L ", aliases) == "Milk"
    assert names.resolve_name("Bread", aliases) == "Bread"


def group_of(groups, name):
    return next((g for g in groups if name in [m["name"] for m in g["names"]]), None)


def test_suggests_names_that_differ_only_by_size():
    groups = names.suggest_merges([("Milk", 8), ("Milk 1L", 3), ("Milk 1,5 l", 1), ("Bread", 5)])
    g = group_of(groups, "Milk 1L")
    assert g and g["suggested"] == "Milk" and g["reason"] == "size"
    assert {m["name"] for m in g["names"]} == {"Milk", "Milk 1L", "Milk 1,5 l"}
    assert group_of(groups, "Bread") is None


def test_suggests_plurals_and_typos_but_not_different_short_words():
    groups = names.suggest_merges([("Banana", 6), ("Bananas", 2), ("Tomatoe", 1), ("Tomato", 4), ("Egg", 3), ("Eggs", 2), ("Rice", 5), ("Mice", 1)])
    assert group_of(groups, "Bananas")["suggested"] == "Banana"
    assert group_of(groups, "Tomatoe")["suggested"] == "Tomato"
    assert group_of(groups, "Eggs")["suggested"] == "Egg"
    assert group_of(groups, "Rice") is None  # one letter apart, but a different thing


def test_does_not_suggest_unrelated_names_that_merely_share_a_word():
    groups = names.suggest_merges([("Ice cream", 4), ("Cream", 3), ("Sour cream", 2)])
    assert groups == []


def test_the_most_used_name_is_suggested_and_biggest_groups_come_first():
    groups = names.suggest_merges([("Yoghurt", 1), ("Yoghurt 1kg", 9), ("Cola", 1), ("Cola 1.5l", 2)])
    assert [g["suggested"] for g in groups] == ["Yoghurt 1kg", "Cola 1.5l"]


def test_handles_many_names_quickly():
    import time

    many = [(f"Item {i:04d} name", 1) for i in range(600)]
    start = time.time()
    names.suggest_merges(many)
    assert time.time() - start < 5
