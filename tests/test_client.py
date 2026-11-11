import json
import unittest

from resell_advisor.client import VintedClient, items_from_catalog_html, status_from_html
from resell_advisor.normalize import parse_item


def page_with(payload_text):
    """Wrap text the way the site does: JSON strings pushed in several script chunks."""
    half = len(payload_text) // 2
    return "<html>" + "".join(
        "<script>self.__next_f.push([1,%s])</script>" % json.dumps(part)
        for part in (payload_text[:half], payload_text[half:])) + "</html>"


ENTRY = {"id": 7, "productItem": {
    "id": 7, "title": "Nike Dunk \"Panda\"", "url": "/items/7-nike-dunk", "favouriteCount": 3,
    "price": {"amount": "184.47", "currencyCode": "RON"},
    "user": {"login": "someone"},
    "itemBox": {"firstLine": "Nike", "secondLine": "42,5 · Foarte bună"}}}
NO_SIZE = {"id": 8, "productItem": {"id": 8, "title": "Geanta", "url": "/items/8-geanta",
                                    "price": {"amount": "50", "currencyCode": "RON"},
                                    "itemBox": {"firstLine": "Zara", "secondLine": "Bună"}}}


class CatalogPageTest(unittest.TestCase):
    def test_items_are_extracted(self):
        payload = 'x:{"catalog":1,"items":{"items":%s,"pagination":{"total_pages":10}}}' % json.dumps(
            [ENTRY, NO_SIZE], ensure_ascii=False)
        raw = items_from_catalog_html(page_with(payload))
        self.assertEqual(len(raw), 2)
        item = parse_item(raw[0], {"nike": ["dunk"]})
        self.assertEqual((item["id"], item["brand"], item["model"], item["size"], item["condition"],
                          item["price"], item["currency"], item["favourites"], item["url"]),
                         (7, "Nike", "dunk", "42,5", "Foarte bună", 184.47, "RON", 3, "/items/7-nike-dunk"))
        self.assertNotIn("someone", repr(raw))
        self.assertEqual((raw[1]["size_title"], raw[1]["status"]), (None, "Bună"))

    def test_empty_and_missing(self):
        self.assertEqual(items_from_catalog_html(page_with('{"items":{"items":[]}}')), [])
        with self.assertRaises(RuntimeError):
            items_from_catalog_html("<html>no data</html>")

    def test_search_url(self):
        client = VintedClient({"domain": "www.vinted.ro"})
        url = client.search_url({"name": "n", "search_text": "air max", "catalog_ids": [1242],
                                 "size_ids": [784, 785], "price_to": "300"}, 2)
        self.assertEqual(url, "https://www.vinted.ro/catalog?search_text=air+max&catalog%5B%5D=1242"
                              "&size_ids%5B%5D=784&size_ids%5B%5D=785&price_to=300"
                              "&order=newest_first&page=2")


class ItemPageTest(unittest.TestCase):
    def test_status(self):
        mine = r'{\"itemId\":\"7\",\"sellerId\":\"1\",\"photoId\":\"p\",\"isClosed\":true}'
        other = r'{\"itemId\":\"9\",\"sellerId\":\"1\",\"isClosed\":false}'
        self.assertEqual(status_from_html(other + mine, "7"), "sold")
        self.assertEqual(status_from_html(other + mine, "9"), "active")
        self.assertEqual(status_from_html('"is_closed":true'), "sold")
        self.assertEqual(status_from_html("<html></html>", "7"), "unknown")


if __name__ == "__main__":
    unittest.main()
