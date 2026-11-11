# Resell Advisor

A small desktop tool that tracks second-hand listings over time to find out **what actually
sells, how fast, and at what price** — so you can decide what stock is worth buying to resell.

Marketplaces show what people *ask* for an item, not what sells. Resell Advisor watches the
listings from searches you choose, notices when each one disappears as sold, and turns that
into per-product statistics.

## What you get

For each brand / model (optionally split by size):

| Column | Meaning |
| --- | --- |
| Sold ≤7d / ≤30d | Estimated chance that a listing sells within 7 / 30 days |
| Median days | Median time from listing to sale |
| Median sold | Median last listed price of sold items |
| Median unsold | Median price of items still for sale |
| Avg favs | Average favourites per listing (early demand signal) |

The numbers only become meaningful after the tool has collected every few hours for a couple
of weeks.

## Features

- Desktop app (dark theme) with a sortable, searchable ranking table
- Add searches by pasting a filtered link from the marketplace website
- Model detection from messy titles using your own keyword lists
- Delete products you no longer care about; they are skipped by later collections
- Export the ranking as a self-contained HTML report
- Demo mode with a simulated market, to try everything without touching the network
- Command line interface for scheduled, unattended collection
- SQLite storage with separate tables per marketplace and a combined view
- No third-party Python packages required

## Marketplace support

| Site | Status |
| --- | --- |
| Vinted | Works. Reads the public catalog and item pages. |
| OLX.ro | **Does not work.** OLX answers this tool's requests with HTTP 403. The tab, tables and collector exist, but the collector has never been tested against a real response. |

## Requirements

- Python 3.12 or newer (Windows is the tested platform; the app uses Tkinter, which ships with Python)
- PyInstaller, only if you want to build the `.exe`

## Running

Desktop app:

```
python app.py
```

Command line:

```
python -m resell_advisor collect                 # one collection run (all sites with searches)
python -m resell_advisor collect --source vinted
python -m resell_advisor stats --by-size         # print the ranking
python -m resell_advisor stats --source all      # both sites, one row per site and product
python -m resell_advisor report --out report.html
python -m resell_advisor demo                    # fill demo.db with simulated data
python -m resell_advisor --db demo.db stats
```

Run `collect` every 4–6 hours (Windows Task Scheduler, cron), or tick **Auto-collect** in the
app and leave the window open.

## Building the Windows exe

```
pip install pyinstaller
pyinstaller --onefile --windowed --name ResellAdvisor --add-data "config.toml;." app.py
```

The exe appears in `dist/`. It keeps its `config.toml`, `searches.json`, database and reports
in whatever folder it is started from, and creates a default `config.toml` on first start.

## Setting up searches

In the app, press **Searches…**:

1. Filter on the marketplace website (category, brand, size, condition, price).
2. Copy the link from the address bar, press **Add…**, paste it and press **Fill**.
3. On the **Models** tab, write one line per brand: `nike: air max 90, air force 1, dunk low`.
   A listing belongs to a model when all words of the model name appear in its title;
   everything else is grouped as `other`.

Searches are saved to `searches.json`. Once that file exists, the `[[search]]` and `[models]`
sections of `config.toml` are ignored. `config.toml` still controls the request delay, the
number of pages per search and the re-check limits.

Keep searches narrow. A plain text search such as "nike" also returns clothes, children's
sizes and listings from other countries.

## How it works

1. **Scan** – each search is fetched newest-first and every listing is stored with its brand,
   model, size, condition, price and favourites.
2. **Re-check** – listings that no longer appear in the results have their own page checked.
   A page marked closed is recorded as a sale; a missing page as removed unsold.
3. **Statistics** – sell-through is a Kaplan-Meier estimate, so listings that are still active
   or were removed unsold count only for as long as they were watched.

## Database

Everything is in one SQLite file (`resell.db` by default).

| Table / view | Contents |
| --- | --- |
| `vinted_items`, `olx_items` | One row per listing (identical columns) |
| `vinted_observations`, `olx_observations` | Price and favourites at each sighting |
| `vinted_runs`, `olx_runs` | One row per collection run |
| `hidden_products` | Products deleted in the app, skipped by collections |
| `all_items` (view) | Both item tables stacked, with a `source` column |

```sql
SELECT source, brand, model, COUNT(*) FROM all_items GROUP BY 1, 2, 3;

SELECT v.model, v.price AS vinted_price, o.price AS olx_price
FROM vinted_items v
JOIN olx_items o ON o.brand = v.brand COLLATE NOCASE AND o.model = v.model;
```

Only item-level data is stored. Seller names, ids and contact details are never saved.

## Limitations

- **Prices are upper bounds.** The recorded price is the last listed price; private offers
  mean the real sale price may be lower.
- **Time to sell is approximate.** Vinted's catalog does not expose the upload date, so the
  clock starts when the tool first sees a listing, and a sale is dated halfway between the
  last sighting and the check that found it closed.
- **Sold detection depends on the site's page layout** and can break when the site changes.
  If the "Sold" counts stop moving, that is the first thing to check.
- **The client is deliberately plain and slow**: a fixed delay between requests, an honest
  user agent, no browser impersonation and no proxies. If a site refuses the requests, the
  run stops with an error instead of working around the block.
- **OLX has no "sold" state.** An ad taken offline by its seller would be counted as sold.

## Tests

```
python -m unittest discover -s tests -t .
```

The tests run offline against a simulated marketplace.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This is a personal market-research tool. Automated access may be against the terms of service
of the marketplaces it reads; check them before use. You are responsible for how you use it.
Use it at low volume, do not use the account you sell from, and do not collect personal data.
This project is not affiliated with Vinted or OLX.
