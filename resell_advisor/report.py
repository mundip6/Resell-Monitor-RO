"""Render statistics as a terminal table or a self-contained sortable HTML page."""
import html
import time

COLUMNS = [
    ("source", "Site"), ("brand", "Brand"), ("model", "Model"), ("size", "Size"),
    ("listings", "Listings"), ("sold", "Sold"),
    ("sell_through_7d", "Sold ≤7d"), ("sell_through_30d", "Sold ≤30d"),
    ("median_days_to_sell", "Median days"),
    ("median_sold_price", "Median sold"), ("median_unsold_price", "Median unsold"),
    ("avg_favourites", "Avg favs"),
]


def _fmt(key, row):
    v = row[key]
    if v is None:
        return "–"
    if key.startswith("sell_through"):
        return f"{v:.0%}"
    if key in ("median_days_to_sell", "avg_favourites"):
        return f"{v:.1f}"
    if key.startswith("median_"):
        return f"{v:.0f} {row['currency']}".strip()
    return str(v)


def _columns(rows):
    optional = {key: any(r[key] is not None for r in rows) for key in ("source", "size")}
    return [c for c in COLUMNS if optional.get(c[0], True)]


def text(rows):
    cols = _columns(rows)
    table = [[label for _, label in cols]] + [[_fmt(k, r) for k, _ in cols] for r in rows]
    widths = [max(len(line[i]) for line in table) for i in range(len(cols))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(line, widths)).rstrip()
                     for line in table)


def html_page(rows, summary):
    cols = _columns(rows)
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in cols)
    body = []
    for r in rows:
        cells = []
        for k, _ in cols:
            raw = r[k]
            sort = raw if isinstance(raw, (int, float)) else ""
            cells.append(f'<td data-v="{html.escape(str(sort))}">{html.escape(_fmt(k, r))}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Resell advisor</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#ddd; --head:#f4f4f4; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16181c; --fg:#e8e8e8; --muted:#9a9a9a; --line:#333; --head:#22252b; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.45 system-ui,sans-serif; margin:24px 16px; }}
p {{ color:var(--muted); max-width:70ch; }}
.wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; }}
th,td {{ padding:6px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }}
th:nth-child(-n+2),td:nth-child(-n+2) {{ text-align:left; }}
th {{ background:var(--head); cursor:pointer; position:sticky; top:0; user-select:none; }}
</style>
<h1>Resell advisor</h1>
<p>{html.escape(summary)}</p>
<p>Prices are last listed prices, so the real sale price may be lower. "Sold ≤7d / ≤30d" is the
estimated chance a listing sells within that time; listings still active or removed unsold count
only for as long as they were watched. Small groups are noisy. Click a column header to sort.</p>
<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>
{chr(10).join(body)}
</tbody></table></div>
<script>
document.querySelectorAll('th').forEach((th, i) => {{
  let dir = -1;
  th.addEventListener('click', () => {{
    const tb = document.querySelector('tbody');
    const val = tr => {{
      const c = tr.children[i], v = c.dataset.v;
      return v === '' ? c.textContent.toLowerCase() : parseFloat(v);
    }};
    const rows = [...tb.rows].sort((a, b) => {{
      const x = val(a), y = val(b);
      if (typeof x !== typeof y) return typeof x === 'number' ? -1 : 1;
      return (x > y ? 1 : x < y ? -1 : 0) * dir;
    }});
    dir = -dir;
    rows.forEach(r => tb.appendChild(r));
  }});
}});
</script>
</html>
"""


def summary(con, source="vinted"):
    from .db import items_table
    c = con.execute("""SELECT COUNT(*) n, SUM(status='sold') sold, SUM(status='active') active,
                              SUM(status='removed') removed, MIN(first_seen) since
                       FROM """ + items_table(source)).fetchone()
    if not c["n"]:
        return "No data yet. Run a collection first."
    since = time.strftime("%Y-%m-%d", time.localtime(c["since"]))
    return (f"{c['n']} listings tracked since {since}: {c['sold']} sold, "
            f"{c['active']} active, {c['removed']} removed unsold.")
