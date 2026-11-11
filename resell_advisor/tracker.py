"""One collection run: scan searches, upsert listings, re-check ones that dropped out."""
import time

from . import db
from .normalize import parse_item


def searches_for(cfg, source):
    return cfg.get("search" if source == "vinted" else f"{source}_search", [])


def _upsert(con, table, obs_table, item, search_name, now):
    row = con.execute(f"SELECT status FROM {table} WHERE id = ?", (item["id"],)).fetchone()
    if row is None:
        con.execute(
            f"""INSERT INTO {table} (id, search_name, title, brand, model, size, condition, price,
                   price_first, currency, favourites, url, listed_at, first_seen, last_seen,
                   last_checked)
               VALUES (:id, :search_name, :title, :brand, :model, :size, :condition, :price,
                   :price, :currency, :favourites, :url, :listed_at, :now, :now, :now)""",
            {**item, "search_name": search_name, "now": now,
             "listed_at": item["listed_at"] or now})
    else:
        # Seen in search again, so it is active (also revives a wrongly closed item).
        con.execute(
            f"""UPDATE {table} SET title = :title, price = :price, favourites = :favourites,
                   condition = :condition, last_seen = :now, last_checked = :now,
                   status = 'active', closed_at = NULL
               WHERE id = :id""", {**item, "now": now})
    con.execute(f"INSERT INTO {obs_table} VALUES (?, ?, ?, ?)",
                (item["id"], now, item["price"], item["favourites"]))
    return row is None


def run(con, client, cfg, source="vinted", now=None, log=print):
    now = int(now if now is not None else time.time())
    table, obs_table = db.items_table(source), f"{source}_observations"
    tcfg = cfg.get("tracker", {})
    models = cfg.get("models", {})
    hidden = db.hidden_set(con, source)
    stats = dict(seen=0, new=0, rechecked=0, sold=0, removed=0, errors=0)

    for search in searches_for(cfg, source):
        for page in range(1, int(tcfg.get("max_pages", 2)) + 1):
            try:
                raw_items = client.search(search, page)
            except Exception as e:  # keep what we have; report and move on
                log(f"{source} search '{search['name']}' page {page} failed: {e}")
                stats["errors"] += 1
                break
            for raw in raw_items:
                try:
                    item = parse_item(raw, models)
                except (KeyError, TypeError, ValueError):
                    stats["errors"] += 1
                    continue
                if db.is_hidden(hidden, item["brand"], item["model"], item["size"]):
                    continue  # the user deleted this product
                stats["seen"] += 1
                stats["new"] += _upsert(con, table, obs_table, item, search["name"], now)
            if not raw_items:
                break
        con.commit()

    # Active items that were not in this run's results: look at their page.
    cutoff = now - int(float(tcfg.get("recheck_after_hours", 6)) * 3600)
    stale = con.execute(
        f"""SELECT id, url, last_seen FROM {table}
           WHERE status = 'active' AND last_seen < ? AND last_checked <= ?
           ORDER BY last_checked LIMIT ?""",
        (now, cutoff, int(tcfg.get("max_rechecks", 150)))).fetchall()
    for row in stale:
        try:
            status = client.item_status(row["url"], row["id"])
        except Exception as e:
            log(f"{source} re-check stopped: {e}")
            stats["errors"] += 1
            break
        stats["rechecked"] += 1
        if status in ("sold", "removed"):
            # It closed somewhere between the last sighting and now: use the midpoint.
            closed_at = (row["last_seen"] + now) // 2
            con.execute(f"UPDATE {table} SET status = ?, closed_at = ?, last_checked = ? "
                        "WHERE id = ?", (status, closed_at, now, row["id"]))
            stats[status] += 1
        elif status == "active":
            con.execute(f"UPDATE {table} SET last_seen = ?, last_checked = ? WHERE id = ?",
                        (now, now, row["id"]))
        else:
            con.execute(f"UPDATE {table} SET last_checked = ? WHERE id = ?", (now, row["id"]))
    con.execute(f"INSERT OR REPLACE INTO {source}_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, *stats.values()))
    con.commit()
    return stats


def make_client(cfg, source):
    if source == "olx":
        from .olx import OlxClient
        return OlxClient(cfg.get("olx", {}), cfg.get("models", {}))
    from .client import VintedClient
    return VintedClient(cfg.get("http", {}))
