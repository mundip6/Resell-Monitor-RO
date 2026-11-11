"""OLX.ro client, same plain and slow approach as the Vinted one.

OLX has no "sold" state: an ad simply goes offline. An ad taken down by its seller
is recorded as sold (the usual reason), an expired or moderated one as removed.
"""
import json
import urllib.parse
from datetime import datetime

from .client import Http
from .normalize import brand_from_title

PAGE_SIZE = 40
RENAMES = {"price_from": "filter_float_price:from", "price_to": "filter_float_price:to"}


def _param(offer, *names):
    """Value of the first ad attribute whose key contains one of `names`."""
    for param in offer.get("params") or []:
        key = (param.get("key") or "").lower()
        if any(name in key for name in names):
            return param.get("value") or {}
    return {}


def _epoch(text):
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except (TypeError, ValueError):
        return None


def offer_to_raw(offer, models):
    """One ad from the offers API, in the shape normalize.parse_item expects.
    Seller, contact and location details are deliberately left out."""
    price = _param(offer, "price")
    brand = _param(offer, "brand", "marca").get("label")
    return {
        "id": offer["id"],
        "title": offer.get("title"),
        "url": offer.get("url"),
        "favourite_count": None,
        "price": {"amount": price.get("value"), "currency_code": price.get("currency")},
        "brand_title": brand or brand_from_title(offer.get("title"), models),
        "size_title": _param(offer, "size", "marime").get("label"),
        "status": _param(offer, "state").get("label"),
        "listed_at": _epoch(offer.get("created_time")),
    }


class OlxClient(Http):
    default_domain = "www.olx.ro"

    def __init__(self, http_cfg, models):
        super().__init__(http_cfg)
        self.models = models

    def search_url(self, search_cfg, page):
        params = {"offset": (page - 1) * PAGE_SIZE, "limit": PAGE_SIZE,
                  "sort_by": "created_at:desc"}
        for key, value in search_cfg.items():
            if key != "name":
                params[RENAMES.get(key, key)] = value
        return self.base + "/api/v1/offers/?" + urllib.parse.urlencode(params)

    def search(self, search_cfg, page):
        code, body = self._get(self.search_url(search_cfg, page), "application/json")
        if code != 200:
            raise RuntimeError(f"search returned HTTP {code}")
        return [offer_to_raw(offer, self.models)
                for offer in json.loads(body).get("data", []) if "id" in offer]

    def item_status(self, url, item_id=None):
        code, body = self._get(f"{self.base}/api/v1/offers/{item_id}/", "application/json")
        if code in (404, 410):
            return "sold"  # the ad is gone
        if code != 200:
            return "unknown"
        status = (json.loads(body).get("data") or {}).get("status")
        if status == "active":
            return "active"
        if status == "removed_by_user":
            return "sold"
        return "removed" if status else "unknown"
