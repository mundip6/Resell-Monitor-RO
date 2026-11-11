"""Configuration loading. Searches and models edited in the app live in searches.json
next to config.toml and, once that file exists, replace the ones in config.toml."""
import json
import re
import tomllib
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

SEARCH_FILE = "searches.json"
# Query parameters of a Vinted catalog link that are not filters.
NOT_FILTERS = {"page", "per_page", "order", "time", "search_id", "disabled_personalization",
               "search_by_image_uuid", "ref"}


def load(config_path):
    config_path = Path(config_path)
    cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
    extra = config_path.parent / SEARCH_FILE
    if extra.exists():
        data = json.loads(extra.read_text(encoding="utf-8"))
        cfg["search"] = data.get("searches", [])
        cfg["models"] = data.get("models", {})
        cfg["olx_search"] = data.get("olx_searches", [])
    cfg.setdefault("olx_search", [])
    return cfg


def save_searches(config_path, searches, models, olx_searches=()):
    path = Path(config_path).parent / SEARCH_FILE
    path.write_text(json.dumps({"searches": searches, "olx_searches": list(olx_searches),
                                "models": models}, indent=2,
                               ensure_ascii=False), encoding="utf-8")


def parse_vinted_url(url):
    """Turn a filtered catalog link copied from the browser into search filters."""
    parts = urlsplit(url.strip())
    out = {}
    in_path = re.search(r"/catalog/(\d+)", parts.path)
    if in_path:  # e.g. /catalog/1242-sneakers
        out["catalog_ids"] = [int(in_path.group(1))]
    for key, value in parse_qsl(parts.query):
        is_list = key.endswith("[]")
        key = key.removesuffix("[]")
        if key == "catalog":
            key = "catalog_ids"
        if key in NOT_FILTERS or not value:
            continue
        if is_list:
            value = int(value) if value.isdigit() else value
            if value not in out.setdefault(key, []):
                out[key].append(value)
        else:
            out[key] = value
    if not out:
        raise ValueError("No filters found in that link")
    return out


OLX_NOT_FILTERS = {"order", "page", "view", "reason", "currency"}
OLX_RENAMES = {"filter_float_price:from": "price_from", "filter_float_price:to": "price_to"}


def parse_olx_url(url):
    """Turn an OLX search link into search filters (text query, price range, other filters)."""
    parts = urlsplit(url.strip())
    out = {}
    for segment in parts.path.split("/"):
        if segment.startswith("q-") and len(segment) > 2:
            out["query"] = segment[2:].replace("-", " ")
    for key, value in parse_qsl(parts.query):
        if not key.startswith("search[") or not value:
            continue
        key = key[len("search["):].replace("]", "", 1)  # search[a][0] -> a[0]
        key = OLX_RENAMES.get(key, key)
        if key not in OLX_NOT_FILTERS:
            out[key] = value
    if not out:
        raise ValueError("No search text or filters found in that link")
    return out
