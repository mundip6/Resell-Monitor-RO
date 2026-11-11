"""Turn a raw catalog-search item into a clean row, and detect the model from the title."""
import re


def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def detect_model(brand, title, models):
    """models: {brand_lowercase: [model names]}. Returns a model name or 'other'."""
    candidates = models.get((brand or "").strip().lower(), [])
    title_words = _words(title)
    joined = " " + " ".join(title_words) + " "
    for name in sorted(candidates, key=len, reverse=True):
        parts = _words(name)
        # exact phrase first, then all-words-present (handles "air max white 90")
        if " " + " ".join(parts) + " " in joined or all(p in title_words for p in parts):
            return name
    return "other"


def brand_from_title(title, models):
    """For sites without a brand field: the first known brand named in the title."""
    joined = " " + " ".join(_words(title)) + " "
    for brand in sorted(models, key=len, reverse=True):
        if " " + " ".join(_words(brand)) + " " in joined:
            return brand.title()
    return None


def _price(raw):
    p = raw.get("price")
    if isinstance(p, dict):
        return _num(p.get("amount")), p.get("currency_code") or raw.get("currency")
    return _num(p), raw.get("currency")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_item(raw, models):
    """Keep only item-level fields. The seller object is deliberately dropped."""
    price, currency = _price(raw)
    brand = (raw.get("brand_title") or "").strip() or "unknown"
    title = (raw.get("title") or "").strip()
    photo = raw.get("photo") or {}
    listed_at = raw.get("listed_at") or (photo.get("high_resolution") or {}).get("timestamp")
    url = raw.get("url") or ""
    return {
        "id": int(raw["id"]),
        "title": title,
        "brand": brand,
        "model": detect_model(brand, title, models),
        "size": (raw.get("size_title") or "").strip() or None,
        "condition": raw.get("status"),
        "price": price,
        "currency": currency,
        "favourites": raw.get("favourite_count"),
        "url": url,
        "listed_at": int(listed_at) if listed_at else None,
    }
