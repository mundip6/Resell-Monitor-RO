"""Simulated marketplace, for trying the pipeline and for tests. No network."""
import random

DAY = 86400

# (brand, title pattern, base price, chance to sell per day)
PRODUCTS = [
    ("Nike", "Nike Air Max 90 {c} {s}", 280, 0.12),
    ("Nike", "nike air force 1 {c} marimea {s}!!", 220, 0.08),
    ("Nike", "Nike Dunk Low {c} {s}", 350, 0.05),
    ("Adidas", "Adidas Samba OG {c} {s}", 300, 0.15),
    ("Adidas", "adidas superstar {c} {s} ca noi", 150, 0.03),
    ("New Balance", "New Balance 530 {c} {s}", 320, 0.10),
    ("New Balance", "NB 574 {c} {s}", 200, 0.02),
]
COLOURS = ["white", "black", "grey", "alb", "negru"]
SIZES = ["41", "42", "43", "44"]


class FakeClient:
    """Stands in for VintedClient. Call advance(now) before each tracker run."""

    def __init__(self, seed=1):
        self.rng = random.Random(seed)
        self.items = {}      # id -> dict(raw=..., state='active'|'sold'|'removed', p=...)
        self.next_id = 1000
        self.now = 0

    def advance(self, now, new_listings=6):
        elapsed_days = (now - self.now) / DAY if self.now else 0
        for it in self.items.values():
            if it["state"] != "active":
                continue
            # cheaper than base price sells faster
            p = it["p"] * (it["base"] / it["raw"]["price"]["amount"]) ** 2
            if self.rng.random() < 1 - (1 - min(p, 0.9)) ** elapsed_days:
                it["state"] = "sold"
            elif self.rng.random() < 0.002:
                it["state"] = "removed"
            else:
                it["raw"]["favourite_count"] += self.rng.random() < it["p"] * 3
        for _ in range(new_listings):
            brand, pattern, base, p = self.rng.choice(PRODUCTS)
            size = self.rng.choice(SIZES)
            self.next_id += 1
            price = round(base * self.rng.uniform(0.7, 1.4))
            self.items[self.next_id] = {
                "state": "active", "p": p, "base": base,
                "raw": {
                    "id": self.next_id,
                    "title": pattern.format(c=self.rng.choice(COLOURS), s=size),
                    "price": {"amount": price, "currency_code": "RON"},
                    "brand_title": brand, "size_title": size, "status": "Foarte bună",
                    "favourite_count": 0, "url": f"/items/{self.next_id}",
                    "photo": {"high_resolution": {"timestamp": now - self.rng.randint(0, 3600)}},
                    "user": {"login": "must-not-be-stored"},
                },
            }
        self.now = now

    def search(self, search_cfg, page, per_page=96):
        text = search_cfg.get("search_text", "").lower()
        active = [it["raw"] for it in self.items.values()
                  if it["state"] == "active" and text in it["raw"]["brand_title"].lower()]
        active.sort(key=lambda r: r["id"], reverse=True)
        return active[(page - 1) * per_page: page * per_page]

    def item_status(self, url, item_id=None):
        return self.items[int(url.rsplit("/", 1)[1])]["state"]


def simulate(con, cfg, days=45, end=None, runs_per_day=4, seed=1):
    """Fill `con` with `days` of simulated tracking that ends at `end`."""
    import time
    from . import tracker
    end = int(end or time.time())
    client = FakeClient(seed)
    step = DAY // runs_per_day
    for now in range(end - days * DAY, end + 1, step):
        client.advance(now)
        tracker.run(con, client, cfg, now=now, log=lambda *_: None)
    return client
