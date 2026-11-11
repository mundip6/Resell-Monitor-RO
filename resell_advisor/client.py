"""Plain, slow HTTP client that reads Vinted's public catalog and item pages.

No browser impersonation, no proxy rotation: if the site refuses the request,
the run stops with a clear error rather than trying to get around the block.
"""
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request


class Blocked(Exception):
    pass


# The pages embed their data as JSON strings inside self.__next_f.push([1,"..."]) scripts.
CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
ITEMS_MARKER = '"items":{"items":'
CLOSED_RE = r'\\?"(?:isClosed|is_closed)\\?"\s*:\s*(true|false)'


def _payload(html):
    return "".join(json.loads(chunk) for chunk in CHUNK_RE.findall(html))


def items_from_catalog_html(html):
    """Listings of one catalog page, as dicts in the shape normalize.parse_item expects."""
    payload = _payload(html)
    start = payload.find(ITEMS_MARKER)
    if start < 0:
        raise RuntimeError("listing data not found in the catalog page (site layout changed?)")
    entries, _ = json.JSONDecoder().raw_decode(payload, start + len(ITEMS_MARKER))
    out = []
    for entry in entries:
        item = entry.get("productItem") or {}
        if "id" not in item:
            continue
        box = item.get("itemBox") or {}
        # second line reads "<size> · <condition>", or just the condition
        details = [part.strip() for part in (box.get("secondLine") or "").split("·")]
        price = item.get("price") or {}
        out.append({
            "id": item["id"],
            "title": item.get("title"),
            "url": item.get("url"),
            "favourite_count": item.get("favouriteCount"),
            "price": {"amount": price.get("amount"), "currency_code": price.get("currencyCode")},
            "brand_title": box.get("firstLine"),
            "size_title": details[0] if len(details) > 1 else None,
            "status": details[-1] or None,
        })
    return out


def status_from_html(html, item_id=None):
    """Classify an item page: 'sold', 'active' or 'unknown'."""
    match = None
    if item_id:  # prefer the flag that sits next to this item's own id
        match = re.search(r'itemId\\?"\s*:\s*\\?"%s\\?"[^{}]{0,300}?%s' % (item_id, CLOSED_RE), html)
    match = match or re.search(CLOSED_RE, html)
    if not match:
        return "unknown"
    return "sold" if match.group(1) == "true" else "active"


class Http:
    """Rate-limited GET with one cookie jar. Shared by the marketplace clients."""
    default_domain = ""

    def __init__(self, http_cfg):
        self.base = "https://" + http_cfg.get("domain", self.default_domain)
        self.delay = float(http_cfg.get("delay_seconds", 4))
        self.timeout = float(http_cfg.get("timeout_seconds", 30))
        self.headers = {"User-Agent": http_cfg.get("user_agent", "resell-advisor/0.1")}
        self.headers.update(http_cfg.get("headers", {}))
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self._last = 0.0

    def _get(self, url, accept="text/html"):
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={**self.headers, "Accept": accept})
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 429):
                raise Blocked(f"HTTP {e.code} for {url} - the site refused the request") from e
            return e.code, ""
        finally:
            self._last = time.monotonic()



class VintedClient(Http):
    default_domain = "www.vinted.ro"

    def __init__(self, http_cfg):
        super().__init__(http_cfg)
        self._has_session = False

    def _session(self):
        # Visit the home page once per run, like a normal visitor, to get the session cookies.
        if not self._has_session:
            self._get(self.base + "/")
            self._has_session = True

    def search_url(self, search_cfg, page):
        params = []
        for key, value in search_cfg.items():
            if key == "name":
                continue
            if isinstance(value, list):
                key = "catalog[]" if key == "catalog_ids" else key + "[]"
                params += [(key, v) for v in value]
            else:
                params.append((key, value))
        params += [("order", "newest_first"), ("page", page)]
        return self.base + "/catalog?" + urllib.parse.urlencode(params)

    def search(self, search_cfg, page):
        """Return the listings of one page of newest-first search results."""
        self._session()
        code, body = self._get(self.search_url(search_cfg, page))
        if code != 200:
            raise RuntimeError(f"search returned HTTP {code}")
        return items_from_catalog_html(body)

    def item_status(self, url, item_id=None):
        """'active' | 'sold' | 'removed' | 'unknown' for one item page."""
        self._session()
        if url.startswith("/"):
            url = self.base + url
        code, body = self._get(url)
        if code in (404, 410):
            return "removed"
        if code != 200:
            return "unknown"
        return status_from_html(body, str(item_id) if item_id else None)
