"""
hvsr_gui_pages.py
=================
UI building blocks for the HVSR Analyzer GUI: the card / file-row
widgets and the scrollable page canvases that every workflow page is
built from, plus the mouse-wheel scrolling that walks the widget tree.
The ttk style setup moved to hvsr_gui_style.py; the window frame
builders live in hvsr_gui_layout.py and the workflow pages in
hvsr_gui_workflow.py.  Mixed into HVSRApp as HVSRAppPagesMixin.
"""


import tkinter as tk
from tkinter import ttk

import hvsr_theme


# Local aliases of the active theme palette (only the ones this
# module uses).  Refreshed by HVSRAppThemeMixin._set_theme() on a
# live theme switch.
BG = hvsr_theme.current["BG"]


class HVSRAppPagesMixin:
    def _card(self, parent, title, row):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=12)
        frame.grid(row=row, column=0, sticky="nsew", padx=12, pady=(0, 10))
        ttk.Label(frame, text=f"// {title.upper()}", style="H.TLabel").pack(anchor="w", pady=(0, 8))
        return frame

    def _add_file_row(self, parent, label, var_name, row):
        row_f = ttk.Frame(parent, style="Card.TFrame")
        row_f.pack(fill="x", pady=3)
        ttk.Label(row_f, text=label, style="Card.TLabel", width=14).pack(side="left")
        entry = ttk.Entry(row_f)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, "")
        self._vars[var_name + "_entry"] = entry
        ttk.Button(row_f, text="BROWSE...", width=9,
                   command=lambda v=var_name: self._browse(v)).pack(side="left", padx=(6, 0))

    def _scroll_page(self, parent):
        # Each page gets its OWN container frame so its scrollbar is packed
        # inside that page only. (Packing the scrollbars directly into the
        # shared notebook body stacked all 4 scrollbars on top of each other
        # on the right edge - the "scroll overlap" in the left layout.)
        container = ttk.Frame(parent, style="TFrame")
        canvas = tk.Canvas(container, highlightthickness=0, bd=0, bg=BG)
        sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        page = ttk.Frame(canvas, style="TFrame")
        win = canvas.create_window((0, 0), window=page, anchor="nw")
        page._scroll_canvas = canvas

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _width(e):
            canvas.itemconfigure(win, width=e.width)

        page.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)
        return container, page

    def _bind_page_wheel(self, page):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            page.bind(seq, self._page_wheel)
            for child in page.winfo_children():
                self._bind_wheel_children(child, seq)

    def _bind_wheel_children(self, widget, seq):
        widget.bind(seq, self._page_wheel)
        for child in widget.winfo_children():
            self._bind_wheel_children(child, seq)

    def _page_wheel(self, event):
        w = event.widget
        canvas = None
        node = w
        while node is not None:
            canvas = getattr(node, "_scroll_canvas", None)
            if canvas is not None:
                break
            node = node.master
        if canvas is None:
            return
        step = max(1, abs(getattr(event, "delta", 120)) // 120)
        if getattr(event, "num", None) == 4:
            canvas.yview_scroll(-step, "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(step, "units")
        else:
            canvas.yview_scroll(-step if event.delta > 0 else step,
                                "units")
        return "break"
