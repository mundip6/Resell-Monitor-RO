import unittest

from resell_advisor import db, stats, tracker
from resell_advisor.client import status_from_html
from resell_advisor.demo import DAY, FakeClient, simulate
from resell_advisor.normalize import detect_model, parse_item

MODELS = {"nike": ["air max 90", "air max", "air force 1", "dunk low"],
          "adidas": ["samba", "superstar"], "new balance": ["530", "574"]}
CFG = {"tracker": {"per_page": 96, "max_pages": 2, "max_rechecks": 500, "recheck_after_hours": 6},
       "search": [{"name": "nike", "search_text": "nike"},
                  {"name": "adidas", "search_text": "adidas"},
                  {"name": "nb", "search_text": "new balance"}],
       "models": MODELS}
END = 1_800_000_000
CFG_TEXT = '''[[search]]
name = "old"
search_text = "x"
[models]
nike = ["tn"]
'''


class NormalizeTest(unittest.TestCase):
    def test_model_detection(self):
        self.assertEqual(detect_model("Nike", "Nike air max 90 white 43 like new!!", MODELS), "air max 90")
        self.assertEqual(detect_model("Nike", "nike AIR MAX alb 90", MODELS), "air max 90")
        self.assertEqual(detect_model("Nike", "Air Max 2090", MODELS), "air max")
        self.assertEqual(detect_model("Nike", "tricou nike", MODELS), "other")
        self.assertEqual(detect_model("Puma", "air max 90", MODELS), "other")

    def test_parse_drops_seller(self):
        raw = {"id": "5", "title": " Samba ", "price": {"amount": "120.5", "currency_code": "RON"},
               "brand_title": "Adidas", "user": {"login": "someone"}, "url": "/items/5"}
        item = parse_item(raw, MODELS)
        self.assertEqual((item["id"], item["price"], item["currency"], item["model"]),
                         (5, 120.5, "RON", "samba"))
        self.assertNotIn("someone", repr(item))

    def test_status_from_html(self):
        self.assertEqual(status_from_html('x "is_closed":true y'), "sold")
        self.assertEqual(status_from_html(r'x \"is_closed\":false,\"is_reserved\":true'), "active")
        self.assertEqual(status_from_html("<html>nothing</html>"), "unknown")


class SettingsTest(unittest.TestCase):
    def test_parse_vinted_url(self):
        from resell_advisor.settings import parse_vinted_url
        url = ("https://www.vinted.ro/catalog?search_text=air%20max&catalog[]=1242&brand_ids[]=53"
               "&size_ids[]=784&size_ids[]=785&price_to=300&order=newest_first&page=2&time=17")
        self.assertEqual(parse_vinted_url(url), {
            "search_text": "air max", "catalog_ids": [1242], "brand_ids": [53],
            "size_ids": [784, 785], "price_to": "300"})
        self.assertEqual(parse_vinted_url("https://www.vinted.ro/catalog/1242-sneakers?color_ids[]=1"),
                         {"catalog_ids": [1242], "color_ids": [1]})
        with self.assertRaises(ValueError):
            parse_vinted_url("https://www.vinted.ro/")

    def test_saved_searches_replace_config(self):
        import tempfile
        from pathlib import Path
        from resell_advisor import settings
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "config.toml"
            cfg_path.write_text(CFG_TEXT)
            self.assertEqual(settings.load(cfg_path)["search"][0]["name"], "old")
            settings.save_searches(cfg_path, [{"name": "new", "brand_ids": [5]}], {"adidas": ["samba"]})
            cfg = settings.load(cfg_path)
            self.assertEqual(cfg["search"], [{"name": "new", "brand_ids": [5]}])
            self.assertEqual(cfg["models"], {"adidas": ["samba"]})

    def test_models_text_roundtrip(self):
        from resell_advisor.search_form import models_to_text, text_to_models
        models = {"new balance": ["530", "574"], "nike": ["air max 90"]}
        self.assertEqual(text_to_models(models_to_text(models)), models)
        self.assertEqual(text_to_models("Nike:  Air Max 90 , TN"), {"nike": ["air max 90", "tn"]})
        with self.assertRaises(ValueError):
            text_to_models("no colon here")


class SellThroughTest(unittest.TestCase):
    @staticmethod
    def row(status, days):
        return {"listed_at": 0, "closed_at": int(days * DAY), "status": status}

    def test_kaplan_meier(self):
        f = stats._sell_through
        now = 40 * DAY
        rows = [self.row("sold", 2), self.row("sold", 20), {"listed_at": 0, "closed_at": None, "status": "active"},
                {"listed_at": 0, "closed_at": None, "status": "active"}]
        self.assertAlmostEqual(f(rows, 7, now), 0.25)
        self.assertAlmostEqual(f(rows, 30, now), 0.5)
        # a listing removed unsold on day 1 leaves the pool: 1 sale among the 3 remaining
        rows = [self.row("removed", 1), self.row("sold", 2), self.row("sold", 20), self.row("sold", 25)]
        self.assertAlmostEqual(f(rows, 7, now), 1 / 3)
        # nothing watched for 30 days yet -> no estimate
        self.assertIsNone(f([{"listed_at": 0, "closed_at": None, "status": "active"}], 30, 5 * DAY))


class TrackerTest(unittest.TestCase):
    def test_sale_detected_with_midpoint_time(self):
        con = db.connect(":memory:")
        client = FakeClient()
        client.advance(END, new_listings=3)
        self.assertEqual(tracker.run(con, client, CFG, now=END, log=lambda *_: None)["new"], 3)
        victim = next(iter(client.items.values()))
        victim["state"] = "sold"
        client.now = END + DAY
        res = tracker.run(con, client, CFG, now=END + DAY, log=lambda *_: None)
        self.assertEqual((res["sold"], res["rechecked"]), (1, 1))
        row = con.execute("SELECT * FROM vinted_items WHERE status='sold'").fetchone()
        self.assertEqual(row["closed_at"], END + DAY // 2)

    def test_simulation_matches_ground_truth(self):
        con = db.connect(":memory:")
        client = simulate(con, CFG, days=45, end=END)
        truth = {i: it["state"] for i, it in client.items.items()}
        mismatches = sum(truth[r["id"]] != r["status"] for r in con.execute("SELECT id, status FROM vinted_items"))
        total = con.execute("SELECT COUNT(*) FROM vinted_items").fetchone()[0]
        self.assertEqual(total, len(truth))
        # only items that closed during the very last interval may still look active
        self.assertLess(mismatches, total * 0.03)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM vinted_items WHERE title LIKE '%must-not%'").fetchone()[0], 0)

        rows = {(r["brand"], r["model"]): r for r in stats.compute(con, now=END)}
        samba, nb574 = rows[("Adidas", "samba")], rows[("New Balance", "574")]
        self.assertGreater(samba["sell_through_7d"], nb574["sell_through_7d"] + 0.2)
        self.assertLess(samba["median_days_to_sell"], nb574["median_days_to_sell"])
        # cheaper listings sell first
        self.assertLess(samba["median_sold_price"], samba["median_unsold_price"])
        for r in rows.values():
            self.assertTrue(0 <= r["sell_through_30d"] <= 1)


if __name__ == "__main__":
    unittest.main()
