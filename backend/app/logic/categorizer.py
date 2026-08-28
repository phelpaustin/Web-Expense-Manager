"""Rule-based + shop-history expense categorizer.

No sklearn/ML dependency (keeps the deploy lightweight): a built-in keyword
rule set covers common merchants/items, and a "learned" pass looks at the
user's own history for the same shop to suggest whatever category they've
used there most.
"""
from __future__ import annotations

from collections import Counter

# Keyword → category rules, ported from the Streamlit app's ml_categorizer.py.
DEFAULT_RULES: dict[str, list[str]] = {
    "Groceries": [
        "milk", "bread", "eggs", "butter", "cheese", "yogurt", "flour", "sugar",
        "rice", "pasta", "vegetables", "fruits", "meat", "chicken", "fish",
        "ica", "lidl", "coop", "willys", "hemköp", "citygross", "netto",
        "juice", "coffee", "tea", "cereal", "snacks", "chocolate",
    ],
    "Transport": [
        "bus", "train", "metro", "subway", "taxi", "uber", "lyft", "fuel",
        "petrol", "gas", "parking", "toll", "ferry", "sl", "flight", "airline",
        "tram", "bike", "cycling", "car", "vehicle", "commute",
    ],
    "Dining": [
        "restaurant", "cafe", "coffee", "pizza", "sushi", "burger", "mcdonalds",
        "starbucks", "mcafe", "kebab", "lunch", "dinner", "breakfast",
        "bistro", "bar", "pub", "takeaway", "delivery", "foodora", "wolt",
    ],
    "Entertainment": [
        "netflix", "spotify", "steam", "cinema", "movie", "concert", "ticket",
        "disney", "hbo", "amazon prime", "youtube", "game", "gaming", "museum",
        "theatre", "bowling", "gym", "fitness", "yoga", "sport",
    ],
    "Healthcare": [
        "pharmacy", "doctor", "dentist", "hospital", "medicine", "prescription",
        "apoteket", "apotek", "clinic", "health", "optical", "glasses",
        "vitamin", "supplement",
    ],
    "Utilities": [
        "electricity", "water", "gas", "internet", "phone", "mobile", "broadband",
        "heating", "insurance", "rent", "landlord", "tele2", "telia", "telenor",
        "wifi", "cable",
    ],
    "Shopping": [
        "h&m", "zara", "ikea", "elgiganten", "mediamarkt", "amazon", "ebay",
        "clothes", "shoes", "jacket", "dress", "shirt", "pants", "electronics",
        "laptop", "phone", "charger", "furniture", "decor",
    ],
    "Education": [
        "book", "course", "udemy", "coursera", "school", "university", "tutoring",
        "library", "kindle", "textbook", "workshop", "seminar", "training",
    ],
    "Travel": [
        "hotel", "airbnb", "hostel", "booking.com", "expedia", "trip", "holiday",
        "vacation", "airport", "luggage", "suitcase", "travel insurance",
    ],
    "Personal Care": [
        "haircut", "salon", "barber", "cosmetics", "shampoo", "soap", "skincare",
        "makeup", "perfume", "beauty", "spa", "nail",
    ],
}


def categorize_by_rules(description: str, shop: str = "") -> str | None:
    """Score keyword matches across categories and return the best match, if any."""
    text = f"{description} {shop}".lower().strip()
    if not text:
        return None
    scores: dict[str, int] = {}
    for category, keywords in DEFAULT_RULES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score
    return max(scores, key=scores.get) if scores else None


def categorize_from_history(expenses: list[dict], description: str, shop: str) -> tuple[str | None, str | None]:
    """Most common (category, subcategory) the user has used for this shop before."""
    shop_norm = shop.strip().lower()
    if not shop_norm:
        return None, None
    matches = [e for e in expenses if str(e.get("shop", "")).strip().lower() == shop_norm]
    if not matches:
        return None, None
    cat = Counter(e["category"] for e in matches if e.get("category")).most_common(1)
    same_cat = [e for e in matches if e.get("category") == (cat[0][0] if cat else None)]
    subcat = Counter(e["subcategory"] for e in same_cat if e.get("subcategory")).most_common(1)
    return (cat[0][0] if cat else None), (subcat[0][0] if subcat else None)


def suggest_category(expenses: list[dict], description: str, shop: str = "") -> dict:
    """Best-effort suggestion: prefer the user's own history for this shop, else keyword rules."""
    learned_cat, learned_subcat = categorize_from_history(expenses, description, shop)
    if learned_cat:
        return {"category": learned_cat, "subcategory": learned_subcat or "", "confidence": 0.9, "method": "history"}

    rule_cat = categorize_by_rules(description, shop)
    if rule_cat:
        return {"category": rule_cat, "subcategory": "", "confidence": 0.6, "method": "rules"}

    return {"category": None, "subcategory": "", "confidence": 0.0, "method": "none"}


def auto_categorize_missing(expenses: list[dict]) -> list[tuple[int, str, str]]:
    """For expenses with a blank/'Uncategorized' category, return [(id, category, subcategory), ...] suggestions."""
    results = []
    for e in expenses:
        current = str(e.get("category") or "").strip()
        if current and current.lower() != "uncategorized":
            continue
        suggestion = suggest_category(expenses, e.get("description", ""), e.get("shop", ""))
        if suggestion["category"]:
            results.append((e["id"], suggestion["category"], suggestion["subcategory"]))
    return results
