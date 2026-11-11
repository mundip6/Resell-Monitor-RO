"""Desktop interface: collect, browse and search the ranking, delete products, export."""
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import db, report, settings, stats, theme, tracker
from .normalize import detect_model
from .search_form import HiddenDialog, SearchManager

FROZEN = getattr(sys, "frozen", False)
# Config, database and reports live next to the exe (or in the project folder).
HOME = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent.parent
CONFIG = HOME / "config.toml"
DONE = object()
TABS = [("vinted", "VINTED"), ("olx", "OLX"), ("all", "BOTH")]
OLX_NOTE = "On OLX, 'sold' means the ad was taken offline by its seller."


def load_config():
    if not CONFIG.exists() and FROZEN:  # first start: unpack the default config
        shutil.copy(Path(sys._MEIPASS) / "config.toml", CONFIG)
    return settings.load(CONFIG)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Resell Advisor")
        self.geometry("1180x700")
        self.minsize(900, 480)
        theme.apply(self)
        theme.dark_title(self)
        self.rows, self.shown = [], []
        self.sort_key, self.sort_desc = None, True
        self.busy = False
        self.queue = queue.Queue()
        self.auto_job = None

        # ---- header: title and site tabs
        head = ttk.Frame(self, padding=(14, 12, 14, 0))
        head.pack(fill="x")
        ttk.Label(head, text="RESELL ADVISOR", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="   what actually sells, and for how much",
                  style="Sub.TLabel").pack(side="left", pady=(8, 0))
        self.source = tk.StringVar(value="vinted")
        for value, label in reversed(TABS):
            ttk.Radiobutton(head, text=label, value=value, variable=self.source,
                            style="Tab.Toolbutton", command=self.refresh).pack(side="right",
                                                                               padx=(4, 0))
        tk.Frame(self, bg=theme.ACCENT, height=1).pack(fill="x", padx=14, pady=(8, 0))

        # ---- collection controls
        bar = ttk.Frame(self, padding=(14, 10, 14, 4))
        bar.pack(fill="x")
        self.collect_btn = ttk.Button(bar, text="Collect now", style="Accent.TButton",
                                      command=self.collect)
        self.collect_btn.pack(side="left")
        self.auto = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Auto-collect every", variable=self.auto,
                        command=self.schedule_auto).pack(side="left", padx=(14, 4))
        self.auto_hours = tk.IntVar(value=6)
        ttk.Spinbox(bar, from_=4, to=24, width=3, textvariable=self.auto_hours,
                    command=self.schedule_auto).pack(side="left")
        ttk.Label(bar, text="hours", style="Muted.TLabel").pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Settings file", command=self.open_config).pack(side="right")
        ttk.Button(bar, text="Export report", command=self.export).pack(side="right", padx=6)
        ttk.Button(bar, text="Deleted…", command=self.manage_hidden).pack(side="right")
        ttk.Button(bar, text="Searches…", command=self.manage_searches).pack(side="right", padx=6)

        # ---- search bar and view options
        find = ttk.Frame(self, padding=(14, 4, 14, 8))
        find.pack(fill="x")
        ttk.Label(find, text="Search", style="Muted.TLabel").pack(side="left")
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self.fill())
        entry = ttk.Entry(find, textvariable=self.query, width=34)
        entry.pack(side="left", padx=(8, 4))
        entry.bind("<Escape>", lambda _: self.query.set(""))
        ttk.Button(find, text="✕", width=3, command=lambda: self.query.set("")).pack(side="left")
        self.by_size = tk.BooleanVar()
        ttk.Checkbutton(find, text="Split by size", variable=self.by_size,
                        command=self.refresh).pack(side="left", padx=(18, 8))
        ttk.Label(find, text="Min listings", style="Muted.TLabel").pack(side="left")
        self.min_listings = tk.IntVar(value=5)
        ttk.Spinbox(find, from_=1, to=500, width=4, textvariable=self.min_listings,
                    command=self.refresh).pack(side="left", padx=(6, 12))
        self.demo = tk.BooleanVar()
        ttk.Checkbutton(find, text="Demo data", variable=self.demo,
                        command=self.refresh).pack(side="left")
        ttk.Button(find, text="Delete selected", style="Danger.TButton",
                   command=self.delete_selected).pack(side="right")

        self.summary = ttk.Label(self, padding=(14, 0, 14, 6), style="Muted.TLabel")
        self.summary.pack(fill="x")

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=14)
        self.tree = ttk.Treeview(mid, show="headings", selectmode="extended")
        self.tree.tag_configure("odd", background=theme.STRIPE)
        scroll = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Delete>", lambda _: self.delete_selected())

        self.log_box = theme.plain(tk.Text(self, height=5, state="disabled", wrap="word"))
        self.log_box.configure(fg=theme.MUTED, font=("Consolas", 9))
        self.log_box.pack(fill="x", padx=14, pady=12)

        self.after(200, self.poll)
        self.refresh()

    # ---- data -------------------------------------------------------------
    def db_path(self, cfg):
        return HOME / ("demo.db" if self.demo.get() else cfg.get("db_path", "resell.db"))

    def config_or_warn(self):
        try:
            return load_config()
        except (OSError, ValueError) as e:
            messagebox.showerror("Resell Advisor", f"Cannot read {CONFIG}:\n{e}")
            return None

    def refresh(self):
        cfg = self.config_or_warn()
        if cfg is None:
            return
        try:
            minimum = max(1, self.min_listings.get())
        except tk.TclError:  # box is empty while typing
            minimum = 1
        source = self.source.get()
        con = db.connect(self.db_path(cfg))
        try:
            if self.demo.get() and not con.execute("SELECT 1 FROM vinted_items LIMIT 1").fetchone():
                from .demo import simulate
                simulate(con, cfg)
            self.rows = stats.compute(con, source=source, by_size=self.by_size.get(),
                                      min_listings=minimum)
            text = report.summary(con, source)
            last = max((con.execute(f"SELECT MAX(ts) FROM {s}_runs").fetchone()[0] or 0)
                       for s in (db.SOURCES if source == "all" else (source,)))
        finally:
            con.close()
        if last:
            text += "  Last collection: " + time.strftime("%Y-%m-%d %H:%M", time.localtime(last))
        if source != "vinted":
            text += "  " + OLX_NOTE
        self.summary.config(text=("[Simulated demo data]  " if self.demo.get() else "") + text)
        self.fill()

    def fill(self):
        words = self.query.get().lower().split()
        rows = [r for r in self.rows if all(
            w in f"{r['source'] or ''} {r['brand']} {r['model']} {r['size'] or ''}".lower()
            for w in words)]
        if self.sort_key:
            known = [r for r in rows if r[self.sort_key] is not None]
            known.sort(key=lambda r: (r[self.sort_key].lower() if isinstance(r[self.sort_key], str)
                                      else r[self.sort_key]), reverse=self.sort_desc)
            rows = known + [r for r in rows if r[self.sort_key] is None]
        self.shown = rows
        cols = report._columns(self.rows) if self.rows else report.COLUMNS[1:]
        text_cols = {"source", "brand", "model"}
        self.tree.configure(columns=[k for k, _ in cols])
        for key, label in cols:
            arrow = (" ▼" if self.sort_desc else " ▲") if key == self.sort_key else ""
            self.tree.heading(key, text=label + arrow, command=lambda k=key: self.sort_by(k),
                              anchor="w" if key in text_cols else "e")
            self.tree.column(key, width=140 if key in ("brand", "model") else 95,
                             anchor="w" if key in text_cols else "e")
        self.tree.delete(*self.tree.get_children())
        for index, r in enumerate(rows):
            values = [(r[k].upper() if k == "source" else report._fmt(k, r)) for k, _ in cols]
            self.tree.insert("", "end", iid=str(index), values=values,
                             tags=("odd",) if index % 2 else ())

    def sort_by(self, key):
        self.sort_desc = not self.sort_desc if key == self.sort_key else True
        self.sort_key = key
        self.fill()

    # ---- deleting products --------------------------------------------------
    def delete_selected(self):
        picked = [self.shown[int(iid)] for iid in self.tree.selection()]
        cfg = self.config_or_warn()
        if not picked or cfg is None:
            return
        listings = sum(r["listings"] for r in picked)
        names = ", ".join(f"{r['brand']} {r['model']}" + (f" {r['size']}" if r["size"] else "")
                          for r in picked[:6]) + ("…" if len(picked) > 6 else "")
        if not messagebox.askyesno(
                "Delete products",
                f"Delete {len(picked)} product(s) with {listings} listings from the database?\n\n"
                f"{names}\n\nTheir history is erased and new collections will skip them. "
                "You can allow them again under \"Deleted…\".", icon="warning"):
            return
        con = db.connect(self.db_path(cfg))
        deleted = 0
        for r in picked:
            for source in ([r["source"]] if r["source"] else [self.source.get()]):
                deleted += db.delete_product(con, source, r["brand"], r["model"], r["size"])
        con.close()
        self.log(f"Deleted {len(picked)} product(s), {deleted} listings")
        self.refresh()

    def manage_hidden(self):
        cfg = self.config_or_warn()
        if cfg is None:
            return
        path = self.db_path(cfg)
        con = db.connect(path)
        hidden = [tuple(r) for r in con.execute(
            "SELECT source, brand, model, size FROM hidden_products ORDER BY 1, 2, 3, 4")]
        con.close()

        def restore(source, brand, model, size):
            con = db.connect(path)
            db.unhide_product(con, source, brand, model, size)
            con.close()
            self.log(f"Restored {source} {brand} {model} {size}".rstrip())

        HiddenDialog(self, hidden, restore)

    # ---- actions ----------------------------------------------------------
    def log(self, text):
        self.log_box.config(state="normal")
        self.log_box.insert("end", time.strftime("%H:%M:%S  ") + str(text) + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def collect(self):
        if self.busy:
            return
        cfg = self.config_or_warn()
        if cfg is None:
            return
        wanted = db.SOURCES if self.source.get() == "all" else (self.source.get(),)
        sources = [s for s in wanted if tracker.searches_for(cfg, s)]
        for s in set(wanted) - set(sources):
            self.log(f"No {s.upper()} searches yet - add some under \"Searches…\"")
        if not sources:
            return
        self.busy = True
        self.collect_btn.config(state="disabled", text="Collecting…")
        path = HOME / cfg.get("db_path", "resell.db")  # never into the demo database

        def work():
            for source in sources:
                self.queue.put(f"Collecting {len(tracker.searches_for(cfg, source))} "
                               f"{source.upper()} searches (slow on purpose)")
                try:
                    con = db.connect(path)
                    result = tracker.run(con, tracker.make_client(cfg, source), cfg,
                                         source=source, log=self.queue.put)
                    con.close()
                    self.queue.put(f"{source.upper()} done: "
                                   + ", ".join(f"{k} {v}" for k, v in result.items()))
                except Exception as e:
                    self.queue.put(f"{source.upper()} collection failed: {e}")
            self.queue.put(DONE)

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg is DONE:
                    self.busy = False
                    self.collect_btn.config(state="normal", text="Collect now")
                    self.refresh()
                else:
                    self.log(msg)
        except queue.Empty:
            pass
        self.after(200, self.poll)

    def schedule_auto(self):
        if self.auto_job:
            self.after_cancel(self.auto_job)
            self.auto_job = None
        if self.auto.get():
            try:
                hours = max(4, self.auto_hours.get())
            except tk.TclError:
                hours = 6
            self.auto_job = self.after(hours * 3600 * 1000, self.auto_tick)
            self.log(f"Auto-collect on: next run in {hours} hours while this window stays open")

    def auto_tick(self):
        self.auto_job = None
        self.collect()
        self.schedule_auto()

    def export(self):
        cfg = self.config_or_warn()
        if cfg is None:
            return
        con = db.connect(self.db_path(cfg))
        out = HOME / ("demo_report.html" if self.demo.get() else "report.html")
        out.write_text(report.html_page(self.shown, report.summary(con, self.source.get())),
                       encoding="utf-8")
        con.close()
        self.log(f"Wrote {out}")
        os.startfile(out)

    def manage_searches(self):
        cfg = self.config_or_warn()
        if cfg is None:
            return

        def save(vinted, olx, models):
            settings.save_searches(CONFIG, vinted, models, olx)
            # regroup listings already collected under the new model names
            for name in {cfg.get("db_path", "resell.db"), "demo.db"}:
                if not (HOME / name).exists():
                    continue
                con = db.connect(HOME / name)
                for source in db.SOURCES:
                    table = db.items_table(source)
                    rows = con.execute(f"SELECT id, brand, title FROM {table}").fetchall()
                    con.executemany(f"UPDATE {table} SET model = ? WHERE id = ?",
                                    [(detect_model(r["brand"], r["title"], models), r["id"])
                                     for r in rows])
                con.commit()
                con.close()
            self.log(f"Saved {len(vinted)} Vinted and {len(olx)} OLX searches, "
                     f"models for {len(models)} brands")
            self.refresh()

        SearchManager(self, cfg.get("search", []), cfg.get("olx_search", []),
                      cfg.get("models", {}), save,
                      start_tab="olx" if self.source.get() == "olx" else "vinted")

    def open_config(self):
        if self.config_or_warn() is not None:
            os.startfile(CONFIG)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
