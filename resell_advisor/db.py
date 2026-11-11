"""SQLite storage. Item-level data only: no seller names or other personal data.

Each marketplace has its own tables (vinted_items, olx_items, ...) with identical
columns. The view all_items stacks them with a `source` column, so both can be
queried together, e.g.

    SELECT source, brand, model, COUNT(*) FROM all_items GROUP BY source, brand, model;

    SELECT v.model, v.price AS vinted_price, o.price AS olx_price
    FROM vinted_items v JOIN olx_items o ON o.brand = v.brand COLLATE NOCASE AND o.model = v.model;
"""
import sqlite3

SOURCES = ("vinted", "olx")

SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {s}_items (
    id            INTEGER PRIMARY KEY,   -- the marketplace's own item id
    search_name   TEXT NOT NULL,
    title         TEXT,
    brand         TEXT,
    model         TEXT,
    size          TEXT,
    condition     TEXT,
    price         REAL,                  -- last listed price (upper bound of sale price)
    price_first   REAL,                  -- price when first seen
    currency      TEXT,
    favourites    INTEGER,
    url           TEXT,
    listed_at     INTEGER,               -- epoch s; upload time if known, else first_seen
    first_seen    INTEGER NOT NULL,
    last_seen     INTEGER NOT NULL,      -- last time seen active
    last_checked  INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',  -- active | sold | removed
    closed_at     INTEGER                -- estimated sale/removal time
);
CREATE INDEX IF NOT EXISTS idx_{s}_items_status ON {s}_items(status, last_checked);
CREATE INDEX IF NOT EXISTS idx_{s}_items_group ON {s}_items(brand, model);

CREATE TABLE IF NOT EXISTS {s}_observations (
    item_id     INTEGER NOT NULL,
    ts          INTEGER NOT NULL,
    price       REAL,
    favourites  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_{s}_obs_item ON {s}_observations(item_id, ts);

CREATE TABLE IF NOT EXISTS {s}_runs (
    ts        INTEGER PRIMARY KEY,
    seen      INTEGER, new INTEGER, rechecked INTEGER,
    sold      INTEGER, removed INTEGER, errors INTEGER
);
"""

SHARED_SCHEMA = """
-- Products the user deleted and does not want collected again. size '' = every size.
CREATE TABLE IF NOT EXISTS hidden_products (
    source TEXT NOT NULL, brand TEXT NOT NULL, model TEXT NOT NULL, size TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source, brand, model, size)
);
DROP VIEW IF EXISTS all_items;
CREATE VIEW all_items AS
    SELECT 'vinted' AS source, * FROM vinted_items
    UNION ALL
    SELECT 'olx' AS source, * FROM olx_items;
"""


def items_table(source):
    if source == "all":
        return "all_items"
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    return f"{source}_items"


def _migrate(con):
    """Databases made before OLX support kept Vinted data in unprefixed tables."""
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "items" in tables and "vinted_items" not in tables:
        for old in ("items", "observations", "runs"):
            if old in tables:
                con.execute(f"ALTER TABLE {old} RENAME TO vinted_{old}")
        for index in ("idx_items_status", "idx_items_group", "idx_obs_item"):
            con.execute(f"DROP INDEX IF EXISTS {index}")
        con.commit()


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    _migrate(con)
    for source in SOURCES:
        con.executescript(SOURCE_SCHEMA.format(s=source))
    con.executescript(SHARED_SCHEMA)
    return con


def hidden_set(con, source):
    return {(r["brand"], r["model"], r["size"]) for r in con.execute(
        "SELECT brand, model, size FROM hidden_products WHERE source = ?", (source,))}


def is_hidden(hidden, brand, model, size):
    return (brand, model, "") in hidden or (brand, model, size or "?") in hidden


def delete_product(con, source, brand, model, size=None, hide=True):
    """Delete every listing of one product (optionally one size). Returns the number deleted."""
    table = items_table(source)
    where, args = "brand = ? AND model = ?", [brand, model]
    if size is not None:
        where += " AND COALESCE(size, '?') = ?"
        args.append(size)
    con.execute(f"DELETE FROM {source}_observations WHERE item_id IN "
                f"(SELECT id FROM {table} WHERE {where})", args)
    deleted = con.execute(f"DELETE FROM {table} WHERE {where}", args).rowcount
    if hide:
        con.execute("INSERT OR IGNORE INTO hidden_products VALUES (?, ?, ?, ?)",
                    (source, brand, model, size or ""))
    con.commit()
    return deleted


def unhide_product(con, source, brand, model, size):
    con.execute("DELETE FROM hidden_products WHERE source = ? AND brand = ? AND model = ? "
                "AND size = ?", (source, brand, model, size))
    con.commit()
