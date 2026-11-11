"""Dark theme: near-black surfaces with an electric cyan accent."""
import ctypes
import sys
from tkinter import ttk

BG = "#080b12"        # window
PANEL = "#0f1420"     # tables, inputs
RAISED = "#182033"    # buttons, headers
LINE = "#26324a"      # borders
TEXT = "#dce6f2"
MUTED = "#7b89a1"
ACCENT = "#22d3ee"
ACCENT_HOT = "#7deaf9"
ACCENT_DIM = "#0b5566"
SELECT = "#0f4656"
DANGER = "#fb7185"
STRIPE = "#0b101a"
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 10)


def apply(root):
    root.configure(bg=BG)
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL, bordercolor=LINE,
                darkcolor=BG, lightcolor=BG, troughcolor=PANEL, focuscolor=ACCENT,
                selectbackground=SELECT, selectforeground="#ffffff", insertcolor=TEXT, font=FONT)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Title.TLabel", foreground=ACCENT, font=("Segoe UI Semibold", 17))
    s.configure("Sub.TLabel", foreground=MUTED, font=("Segoe UI", 9))

    s.configure("TButton", background=RAISED, foreground=TEXT, bordercolor=LINE,
                lightcolor=RAISED, darkcolor=RAISED, padding=(12, 6), relief="flat")
    s.map("TButton", background=[("disabled", PANEL), ("active", LINE)],
          foreground=[("disabled", MUTED)], bordercolor=[("active", ACCENT)],
          lightcolor=[("active", LINE)], darkcolor=[("active", LINE)])
    s.configure("Accent.TButton", background=ACCENT, foreground="#03141a", font=FONT_BOLD,
                bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    s.map("Accent.TButton", background=[("disabled", ACCENT_DIM), ("active", ACCENT_HOT)],
          foreground=[("disabled", "#9fb4bd")], lightcolor=[("active", ACCENT_HOT)],
          darkcolor=[("active", ACCENT_HOT)])
    s.configure("Danger.TButton", foreground=DANGER)
    s.map("Danger.TButton", bordercolor=[("active", DANGER)])

    s.configure("Tab.Toolbutton", background=BG, foreground=MUTED, padding=(20, 8),
                font=("Segoe UI Semibold", 11), relief="flat", bordercolor=BG)
    s.map("Tab.Toolbutton", background=[("selected", RAISED), ("active", PANEL)],
          foreground=[("selected", ACCENT), ("active", TEXT)],
          bordercolor=[("selected", ACCENT)])

    s.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorcolor=PANEL,
                indicatorbackground=PANEL, indicatorforeground="#03141a",
                upperbordercolor=LINE, lowerbordercolor=LINE)
    s.map("TCheckbutton", background=[("active", BG)], foreground=[("active", ACCENT)],
          indicatorcolor=[("selected", ACCENT)], indicatorbackground=[("selected", ACCENT)],
          upperbordercolor=[("selected", ACCENT)], lowerbordercolor=[("selected", ACCENT)])

    for widget in ("TEntry", "TSpinbox"):
        s.configure(widget, fieldbackground=PANEL, foreground=TEXT, bordercolor=LINE,
                    lightcolor=PANEL, darkcolor=PANEL, insertcolor=TEXT, arrowcolor=TEXT,
                    background=RAISED, padding=4)
        s.map(widget, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])

    s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                rowheight=28, bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL)
    s.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", "#ffffff")])
    s.configure("Treeview.Heading", background=RAISED, foreground=ACCENT, font=FONT_BOLD,
                relief="flat", bordercolor=LINE, lightcolor=RAISED, darkcolor=RAISED,
                padding=(8, 6))
    s.map("Treeview.Heading", background=[("active", LINE)])

    s.configure("TNotebook", background=BG, bordercolor=LINE, lightcolor=BG, darkcolor=BG)
    s.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(14, 6),
                bordercolor=LINE, lightcolor=BG, darkcolor=BG)
    s.map("TNotebook.Tab", background=[("selected", RAISED)], foreground=[("selected", ACCENT)],
          lightcolor=[("selected", RAISED)])

    s.configure("Vertical.TScrollbar", background=RAISED, troughcolor=BG, arrowcolor=MUTED,
                bordercolor=BG, lightcolor=RAISED, darkcolor=RAISED)
    s.map("Vertical.TScrollbar", background=[("active", LINE)])
    s.configure("TSeparator", background=LINE)


def plain(widget):
    """Colours for classic tk widgets (Text, Listbox), which ttk styles do not reach."""
    widget.configure(bg=PANEL, fg=TEXT, selectbackground=SELECT, selectforeground="#ffffff",
                     highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
                     relief="flat", bd=0, font=FONT)
    if widget.winfo_class() == "Text":
        widget.configure(insertbackground=TEXT, padx=8, pady=6)
    return widget


def dark_title(window):
    """Ask Windows for a dark title bar. Harmless if unsupported."""
    window.configure(bg=BG)
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        handle = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 20, ctypes.byref(value), 4)
    except Exception:
        pass
