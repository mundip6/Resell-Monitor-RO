"""Demand statistics per brand/model (optionally per size)."""
import time
from statistics import median

from .db import items_table

DAY = 86400


def _sell_through(rows, days, now):
    """Probability that a listing sells within `days` (Kaplan-Meier estimate).

    Listings still active, or removed unsold, are incomplete observations: they
    count as "not sold yet" for as long as we watched them and then drop out,
    instead of being ignored (which would overstate the rate) or counted as
    never selling (which would understate it).
    Returns None until at least one listing has been watched for `days`.
    """
    spans = []
    for r in rows:
        end = r["closed_at"] if r["status"] != "active" else now
        spans.append((max(end - r["listed_at"], 0) / DAY, r["status"] == "sold"))
    if not spans or max(t for t, _ in spans) < days:
        return None
    spans.sort(key=lambda s: (s[0], not s[1]))  # at equal times, sales before drop-outs
    surviving, at_risk = 1.0, len(spans)
    for t, sold in spans:
        if t > days:
            break
        if sold:
            surviving *= 1 - 1 / at_risk
        at_risk -= 1
    return 1 - surviving


def _med(values):
    values = [v for v in values if v is not None]
    return median(values) if values else None


def compute(con, source="vinted", by_size=False, min_listings=1, now=None):
    """source: 'vinted', 'olx', or 'all' (both, one row per site and product)."""
    now = int(now if now is not None else time.time())
    groups = {}
    both = source == "all"
    for r in con.execute(f"SELECT * FROM {items_table(source)}"):
        key = ((r["source"] if both else None, r["brand"], r["model"])
               + ((r["size"] or "?",) if by_size else ()))
        groups.setdefault(key, []).append(r)

    out = []
    for key, rows in groups.items():
        if len(rows) < min_listings:
            continue
        sold = [r for r in rows if r["status"] == "sold"]
        active = [r for r in rows if r["status"] == "active"]
        st7 = _sell_through(rows, 7, now)
        st30 = _sell_through(rows, 30, now)
        favs = [r["favourites"] for r in rows if r["favourites"] is not None]
        out.append({
            "source": key[0], "brand": key[1], "model": key[2],
            "size": key[3] if by_size else None,
            "listings": len(rows), "sold": len(sold), "active": len(active),
            "sell_through_7d": st7,
            "sell_through_30d": st30,
            "median_days_to_sell": _med([(r["closed_at"] - r["listed_at"]) / DAY for r in sold]),
            "median_sold_price": _med([r["price"] for r in sold]),
            "median_unsold_price": _med([r["price"] for r in active]),
            "avg_favourites": sum(favs) / len(favs) if favs else None,
            "currency": next((r["currency"] for r in rows if r["currency"]), ""),
        })
    out.sort(key=lambda g: (g["sell_through_30d"] if g["sell_through_30d"] is not None else -1,
                            g["sold"], g["listings"]), reverse=True)
    return out
