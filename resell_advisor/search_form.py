"""Windows for managing the tracked searches (Vinted and OLX) and the model names."""
import re
import tkinter as tk
from tkinter import messagebox, ttk

from . import theme
from .settings import parse_olx_url, parse_vinted_url

# Per site: form fields as (key, label, holds a list of ids), link parser, hint.
SITES = {
    "vinted": {
        "title": "Vinted",
        "fields": [("search_text", "Search text", False), ("catalog_ids", "Category ids", True),
                   ("brand_ids", "Brand ids", True), ("size_ids", "Size ids", True),
                   ("status_ids", "Condition ids", True), ("price_from", "Price from", False),
                   ("price_to", "Price to", False)],
        "parse": parse_vinted_url,
        "name_from": "search_text",
        "hint": "Easiest: filter on the Vinted website, copy the link from the address bar, "
                "paste it here and press Fill.",
    },
    "olx": {
        "title": "OLX",
        "fields": [("query", "Search text", False), ("category_id", "Category id", False),
                   ("price_from", "Price from", False), ("price_to", "Price to", False)],
        "parse": parse_olx_url,
        "name_from": "query",
        "hint": "Search on olx.ro, copy the link from the address bar, paste it here and press "
                "Fill. The search text and price range are taken from the link.",
    },
}


def describe(search):
    bits = [f"{k}={','.join(map(str, v)) if isinstance(v, list) else v}"
            for k, v in search.items() if k != "name"]
    return f"{search['name']}   ({'; '.join(bits)})"


def models_to_text(models):
    return "\n".join(f"{brand}: {', '.join(names)}" for brand, names in sorted(models.items()))


def text_to_models(text):
    models = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        brand, sep, names = line.partition(":")
        if not sep or not brand.strip():
            raise ValueError(f"Line {number}: expected 'brand: model, model, ...'")
        names = [n.strip().lower() for n in names.split(",") if n.strip()]
        if names:
            models[brand.strip().lower()] = names
    return models


class SearchDialog(tk.Toplevel):
    """Add or edit one search. The result is in .result (None if cancelled)."""

    def __init__(self, parent, site, search=None, taken_names=()):
        super().__init__(parent)
        self.site = SITES[site]
        self.title(("Edit " if search else "Add ") + self.site["title"] + " search")
        self.transient(parent)
        self.resizable(False, False)
        theme.dark_title(self)
        self.result = None
        self.taken = set(taken_names)
        search = dict(search or {})
        self.known = {key for key, _, _ in self.site["fields"]}
        # filters the form has no field for (e.g. colour) are kept as they are
        self.extra = {k: v for k, v in search.items() if k not in self.known and k != "name"}

        box = ttk.Frame(self, padding=14)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=self.site["hint"], style="Muted.TLabel",
                  wraplength=470).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(box, text=self.site["title"] + " link").grid(row=1, column=0, sticky="w")
        self.url = tk.StringVar()
        ttk.Entry(box, textvariable=self.url, width=52).grid(row=1, column=1, padx=8)
        ttk.Button(box, text="Fill", command=self.fill_from_url).grid(row=1, column=2)
        ttk.Separator(box).grid(row=2, column=0, columnspan=3, sticky="ew", pady=12)

        ttk.Label(box, text="Name").grid(row=3, column=0, sticky="w")
        self.name = tk.StringVar(value=search.get("name", ""))
        ttk.Entry(box, textvariable=self.name, width=52).grid(row=3, column=1, padx=8, pady=3)
        self.vars = {}
        for row, (key, label, _) in enumerate(self.site["fields"], 4):
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="w")
            self.vars[key] = tk.StringVar()
            ttk.Entry(box, textvariable=self.vars[key], width=52).grid(row=row, column=1,
                                                                       padx=8, pady=3)
        self.extra_label = ttk.Label(box, style="Muted.TLabel", wraplength=470)
        self.extra_label.grid(row=20, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.show(search)

        buttons = ttk.Frame(box)
        buttons.grid(row=21, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", style="Accent.TButton",
                   command=self.ok).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _: self.destroy())
        self.grab_set()

    def show(self, filters):
        for key, _, _ in self.site["fields"]:
            value = filters.get(key, "")
            self.vars[key].set(", ".join(map(str, value)) if isinstance(value, list) else value)
        self.extra_label.config(text="Also kept from the link: " + ", ".join(self.extra)
                                if self.extra else "")

    def fill_from_url(self):
        try:
            filters = self.site["parse"](self.url.get())
        except ValueError as e:
            messagebox.showwarning("Link", str(e), parent=self)
            return
        self.extra = {k: v for k, v in filters.items() if k not in self.known}
        self.show(filters)
        if not self.name.get().strip():
            self.name.set(filters.get(self.site["name_from"], ""))

    def ok(self):
        name = self.name.get().strip()
        if not name:
            return messagebox.showwarning("Search", "Give the search a name.", parent=self)
        if name in self.taken:
            return messagebox.showwarning("Search", f"'{name}' already exists.", parent=self)
        search = {"name": name}
        for key, label, is_list in self.site["fields"]:
            text = self.vars[key].get().strip()
            if not text:
                continue
            if is_list:
                parts = [p for p in re.split(r"[,\s]+", text) if p]
                if not all(p.isdigit() for p in parts):
                    return messagebox.showwarning(
                        "Search", f"{label}: numbers separated by commas.", parent=self)
                search[key] = [int(p) for p in parts]
            else:
                search[key] = text
        search.update(self.extra)
        if len(search) == 1:
            return messagebox.showwarning(
                "Search", "Add at least a search text or one filter.", parent=self)
        self.result = search
        self.destroy()


class SearchList(ttk.Frame):
    """Editable list of one site's searches."""

    def __init__(self, parent, window, site, searches):
        super().__init__(parent, padding=10)
        self.window, self.site = window, site
        self.searches = [dict(s) for s in searches]
        side = ttk.Frame(self)
        side.pack(side="right", fill="y", padx=(10, 0))
        ttk.Button(side, text="Add…", style="Accent.TButton", command=self.add).pack(fill="x")
        ttk.Button(side, text="Edit…", command=self.edit).pack(fill="x", pady=6)
        ttk.Button(side, text="Remove", style="Danger.TButton", command=self.remove).pack(fill="x")
        self.listbox = theme.plain(tk.Listbox(self, activestyle="none"))
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda _: self.edit())
        self.redraw()

    def redraw(self):
        self.listbox.delete(0, "end")
        for search in self.searches:
            self.listbox.insert("end", "  " + describe(search))

    def selected(self):
        picked = self.listbox.curselection()
        return picked[0] if picked else None

    def _dialog(self, search, index):
        taken = [s["name"] for i, s in enumerate(self.searches) if i != index]
        dialog = SearchDialog(self.window, self.site, search, taken)
        self.window.wait_window(dialog)
        self.window.grab_set()
        return dialog.result

    def add(self):
        result = self._dialog(None, None)
        if result:
            self.searches.append(result)
            self.redraw()

    def edit(self):
        index = self.selected()
        if index is None:
            return
        result = self._dialog(self.searches[index], index)
        if result:
            self.searches[index] = result
            self.redraw()
            self.listbox.selection_set(index)

    def remove(self):
        index = self.selected()
        if index is not None:
            del self.searches[index]
            self.redraw()


class SearchManager(tk.Toplevel):
    """Searches per site plus the model names.
    on_save(vinted_searches, olx_searches, models) is called on Save."""

    def __init__(self, parent, vinted, olx, models, on_save, start_tab="vinted"):
        super().__init__(parent)
        self.title("Searches")
        self.geometry("760x440")
        self.transient(parent)
        theme.dark_title(self)
        self.on_save = on_save

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.lists = {"vinted": SearchList(tabs, self, "vinted", vinted),
                      "olx": SearchList(tabs, self, "olx", olx)}
        tabs.add(self.lists["vinted"], text="Vinted searches")
        tabs.add(self.lists["olx"], text="OLX searches")

        third = ttk.Frame(tabs, padding=10)
        tabs.add(third, text="Models")
        ttk.Label(third, style="Muted.TLabel", wraplength=700, text=(
            "One line per brand, written as the brand appears on the site:   "
            "nike: air max 90, air force 1, dunk low\n"
            "A listing is assigned to a model when all words of the model name are in its "
            "title. Listings that match nothing are grouped as 'other'. On OLX the brand "
            "itself is also recognised from these brand names in the title.")).pack(anchor="w")
        self.models_text = theme.plain(tk.Text(third, height=10, wrap="word"))
        self.models_text.pack(fill="both", expand=True, pady=(8, 0))
        self.models_text.insert("1.0", models_to_text(models))
        if start_tab == "olx":
            tabs.select(self.lists["olx"])

        bottom = ttk.Frame(self, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Save", style="Accent.TButton",
                   command=self.save).pack(side="right", padx=8)
        self.grab_set()

    def save(self):
        try:
            models = text_to_models(self.models_text.get("1.0", "end"))
        except ValueError as e:
            return messagebox.showwarning("Models", str(e), parent=self)
        self.on_save(self.lists["vinted"].searches, self.lists["olx"].searches, models)
        self.destroy()


class HiddenDialog(tk.Toplevel):
    """Products deleted by the user. on_restore(source, brand, model, size) per restored one."""

    def __init__(self, parent, hidden, on_restore):
        super().__init__(parent)
        self.title("Deleted products")
        self.geometry("520x360")
        self.transient(parent)
        theme.dark_title(self)
        self.hidden, self.on_restore = list(hidden), on_restore
        ttk.Label(self, style="Muted.TLabel", wraplength=480, padding=(12, 10, 12, 4), text=(
            "These products were deleted and are skipped by new collections. Restore one to "
            "start collecting it again (the deleted history does not come back).")).pack(anchor="w")
        self.listbox = theme.plain(tk.Listbox(self, activestyle="none", selectmode="extended"))
        self.listbox.pack(fill="both", expand=True, padx=12)
        bottom = ttk.Frame(self, padding=12)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Restore selected", style="Accent.TButton",
                   command=self.restore).pack(side="right", padx=8)
        self.redraw()
        self.grab_set()

    def redraw(self):
        self.listbox.delete(0, "end")
        for source, brand, model, size in self.hidden:
            self.listbox.insert("end", f"  {source.upper()}   {brand} {model}"
                                       + (f"   size {size}" if size else ""))

    def restore(self):
        for index in sorted(self.listbox.curselection(), reverse=True):
            self.on_restore(*self.hidden.pop(index))
        self.redraw()
