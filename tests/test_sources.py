import sqlite3
import tempfile
import unittest
from pathlib import Path

from resell_advisor import db, stats, tracker
from resell_advisor.demo import DAY, FakeClient
from resell_advisor.olx import OlxClient, offer_to_raw
from resell_advisor.normalize import parse_item
from resell_advisor.settings import parse_olx_url

MODELS = {"nike": ["dunk low", "air max 90"], "adidas": ["samba"], "new balance": ["530"]}
CFG = {"tracker": {"max_pages": 1, "max_rechecks": 50, "recheck_after_hours": 6},
       "search": [{"name": "nike", "search_text": "nike"}],
       "olx_search": [{"name": "adidas", "search_text": "adidas"}], "models": MODELS}
END = 1_800_000_000
QUIET = lambda *_: None  # noqa: E731

# Shape of an ad in OLX's offers API, as assumed by olx.py (not confirmed against the live site).
OFFER = {"id": 301, "url": "https://www.olx.ro/d/oferta/nike-dunk-ID301.html",
         "title": "Adidasi Nike Dunk Low Panda 42", "created_time": "2027-01-15T10:00:00+02:00",
         "status": "active", "user": {"name": "someone"}, "contact": {"phone": True},
         "params": [{"key": "price", "value": {"value": 350, "currency": "RON"}},
                    {"key": "state", "value": {"key": "used", "label": "Utilizat"}},
                    {"key": "size_shoes", "value": {"key": "42", "label": "42"}}]}


def both_sites():
    con = db.connect(":memory:")
    fake = FakeClient()
    fake.advance(END, new_listings=30)
    tracker.run(con, fake, CFG, source="vinted", now=END, log=QUIET)
    tracker.run(con, fake, CFG, source="olx", now=END, log=QUIET)
    return con, fake


class OlxTest(unittest.TestCase):
    def test_offer_mapping(self):
        item = parse_item(offer_to_raw(OFFER, MODELS), MODELS)
        self.assertEqual((item["id"], item["brand"], item["model"], item["size"], item["condition"],
                          item["price"], item["currency"], item["favourites"]),
                         (301, "Nike", "dunk low", "42", "Utilizat", 350.0, "RON", None))
        self.assertEqual(item["listed_at"], 1_800_000_000)
        self.assertNotIn("someone", repr(offer_to_raw(OFFER, MODELS)))

    def test_search_url(self):
        url = OlxClient({}, MODELS).search_url(
            {"name": "x", "query": "nike dunk", "price_from": "100"}, 2)
        self.assertEqual(url, "https://www.olx.ro/api/v1/offers/?offset=40&limit=40"
                              "&sort_by=created_at%3Adesc&query=nike+dunk"
                              "&filter_float_price%3Afrom=100")

    def test_parse_olx_url(self):
        url = ("https://www.olx.ro/moda-frumusete/incaltaminte-barbati/q-nike-dunk/"
               "?currency=RON&search%5Border%5D=created_at:desc"
               "&search%5Bfilter_float_price:from%5D=100&search%5Bfilter_enum_size%5D%5B0%5D=42")
        self.assertEqual(parse_olx_url(url), {"query": "nike dunk", "price_from": "100",
                                              "filter_enum_size[0]": "42"})
        with self.assertRaises(ValueError):
            parse_olx_url("https://www.olx.ro/")


class SeparateTablesTest(unittest.TestCase):
    def test_sites_are_stored_apart_and_joinable(self):
        con, _ = both_sites()
        vinted = con.execute("SELECT COUNT(*), COUNT(DISTINCT brand) FROM vinted_items").fetchone()
        olx = con.execute("SELECT COUNT(*), COUNT(DISTINCT brand) FROM olx_items").fetchone()
        self.assertGreater(vinted[0], 0)
        self.assertGreater(olx[0], 0)
        self.assertEqual((vinted[1], olx[1]), (1, 1))  # nike only / adidas only
        per_site = dict(con.execute("SELECT source, COUNT(*) FROM all_items GROUP BY source"))
        self.assertEqual(per_site, {"vinted": vinted[0], "olx": olx[0]})
        joined = con.execute("SELECT COUNT(*) FROM vinted_items v JOIN olx_items o "
                             "ON o.size = v.size").fetchone()[0]
        self.assertGreater(joined, 0)
        rows = stats.compute(con, source="all", now=END)
        self.assertEqual({r["source"] for r in rows}, {"vinted", "olx"})
        self.assertTrue(all(r["source"] is None for r in stats.compute(con, "vinted", now=END)))

    def test_old_database_is_migrated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "old.db"
            old = sqlite3.connect(path)
            old.executescript(db.SOURCE_SCHEMA.format(s="vinted")
                              .replace("vinted_items", "items")
                              .replace("vinted_observations", "observations")
                              .replace("vinted_runs", "runs")
                              .replace("idx_vinted_items_", "idx_items_")
                              .replace("idx_vinted_obs_item", "idx_obs_item"))
            old.execute("INSERT INTO items (id, search_name, brand, model, first_seen, last_seen,"
                        " last_checked) VALUES (1, 's', 'Nike', 'dunk', 1, 1, 1)")
            old.execute("INSERT INTO observations VALUES (1, 1, 10, 0)")
            old.commit()
            old.close()
            for _ in range(2):  # second open must be a no-op
                con = db.connect(path)
                self.assertEqual(con.execute("SELECT brand FROM vinted_items").fetchone()[0], "Nike")
                self.assertEqual(con.execute("SELECT COUNT(*) FROM vinted_observations").fetchone()[0], 1)
                self.assertEqual(con.execute("SELECT source FROM all_items").fetchone()[0], "vinted")
                tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
                self.assertNotIn("items", tables)
                con.close()


class DeleteTest(unittest.TestCase):
    def test_deleted_product_stays_away(self):
        con, fake = both_sites()
        target = con.execute("SELECT brand, model, COUNT(*) n FROM vinted_items "
                             "GROUP BY 1, 2 ORDER BY n DESC").fetchone()
        others = con.execute("SELECT COUNT(*) FROM vinted_items").fetchone()[0] - target["n"]
        olx_before = con.execute("SELECT COUNT(*) FROM olx_items").fetchone()[0]
        self.assertEqual(db.delete_product(con, "vinted", target["brand"], target["model"]),
                         target["n"])
        left = con.execute("SELECT COUNT(*) FROM vinted_items WHERE brand = ? AND model = ?",
                           (target["brand"], target["model"])).fetchone()[0]
        orphans = con.execute("SELECT COUNT(*) FROM vinted_observations WHERE item_id NOT IN "
                              "(SELECT id FROM vinted_items)").fetchone()[0]
        self.assertEqual((left, orphans), (0, 0))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM olx_items").fetchone()[0], olx_before)

        fake.now = END + DAY  # same listings are still on the site
        tracker.run(con, fake, CFG, source="vinted", now=END + DAY, log=QUIET)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM vinted_items").fetchone()[0], others)

        db.unhide_product(con, "vinted", target["brand"], target["model"], "")
        tracker.run(con, fake, CFG, source="vinted", now=END + 2 * DAY, log=QUIET)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM vinted_items").fetchone()[0],
                         others + target["n"])

    def test_delete_one_size_only(self):
        con, _ = both_sites()
        row = con.execute("SELECT brand, model, size, COUNT(*) n FROM vinted_items "
                          "GROUP BY 1, 2, 3").fetchone()
        same_model = con.execute("SELECT COUNT(*) FROM vinted_items WHERE brand = ? AND model = ?",
                                 (row["brand"], row["model"])).fetchone()[0]
        self.assertEqual(db.delete_product(con, "vinted", row["brand"], row["model"], row["size"]),
                         row["n"])
        self.assertEqual(con.execute("SELECT COUNT(*) FROM vinted_items WHERE brand = ? AND model = ?",
                                     (row["brand"], row["model"])).fetchone()[0], same_model - row["n"])
        self.assertTrue(db.is_hidden(db.hidden_set(con, "vinted"), row["brand"], row["model"], row["size"]))
        self.assertFalse(db.is_hidden(db.hidden_set(con, "vinted"), row["brand"], row["model"], "99"))


if __name__ == "__main__":
    unittest.main()
