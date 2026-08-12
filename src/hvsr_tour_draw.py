# -*- coding: utf-8 -*-
"""
hvsr_tour_draw.py
=================
Rendering side of the guided-tour overlay: TourDrawing holds the class
constants (fonts, paddings, the transparent colour) and the drawing
methods - the dim/spotlight layer, name tag, pointer arrow and the
explanatory callout card.  TourOverlay (hvsr_tour.py) composes these.

Split out of hvsr_tour.py.
"""

import tkinter as tk
import tkinter.font as tkfont

try:
    import hvsr_theme
except Exception:                      # pragma: no cover
    hvsr_theme = None

class TourDrawing:
    """Drawing primitives for the guided-tour overlay."""

    CARD_PAD = 16
    BOX_PAD = 8
    CARD_TITLE_FONT = ("Segoe UI", 13, "bold")
    CARD_BODY_FONT = ("Segoe UI", 11)
    CARD_BTN_FONT = ("Segoe UI", 10, "bold")
    TAG_FONT = ("Segoe UI", 10, "bold")
    TRANSPARENT = "#ff00fe"

    def _palette(self):
        """Return the colour palette of the currently active theme so the
        tour follows a mid-run theme switch."""
        if hvsr_theme is not None:
            t = getattr(hvsr_theme, "current", None) or {}
        else:
            t = {}
        return {
            "panel": t.get("PANEL_BG", "#18181f"),
            "fg": t.get("TEXT_DARK", "#e8e8e8"),
            "muted": t.get("TEXT_MUTED", "#9a9aa5"),
            "accent": t.get("ACCENT", "#ff8c1a"),
            # solid, clearly-visible dim layer (painted on the transparent
            # overlay, so the boxed control shows through at full colour)
            "dim": "#26262e",
        }

    def _target_label(self, step, target):
        """A short readable name for the boxed control (its text, if any)."""
        name = step.get("tag") or ""
        if not name and target is not None:
            try:
                txt = str(target.cget("text")).strip()
                if txt:
                    name = txt
            except Exception:
                pass
        return name

    def _draw(self):
        """Draw the current step: dim everything except the spotlight box,
        draw the pointer arrow, and the callout card."""
        canvas = self._canvas
        if canvas is None:
            return
        canvas.delete("all")
        self._app.update_idletasks()
        pal = self._palette()
        W = max(canvas.winfo_width(), 200)
        H = max(canvas.winfo_height(), 200)
        step = self._steps[self._idx]

        self._apply_pre(step)
        self._app.update_idletasks()

        box = None
        target = self._resolve_target(step)
        if target is not None and target.winfo_ismapped():
            pad = self.BOX_PAD
            ax0 = target.winfo_rootx() - self._app.winfo_rootx()
            ay0 = target.winfo_rooty() - self._app.winfo_rooty()
            ax1 = ax0 + max(target.winfo_width(), 8)
            ay1 = ay0 + max(target.winfo_height(), 8)
            x0 = max(0, ax0 - pad)
            y0 = max(0, ay0 - pad)
            x1 = min(W, ax1 + pad)
            ch = self._card_height(W, step.get("title", ""),
                                   step.get("text", ""))
            y1 = min(H - ch - 26, ay1 + pad)
            if x1 > x0 and y1 > y0:
                box = (x0, y0, x1, y1)
                # dim everything OUTSIDE the spotlight box; the box itself
                # stays transparent so the real control shows through
                for bx0, by0, bx1, by1 in (
                        (0, 0, W, y0), (0, y1, W, H),
                        (0, y0, x0, y1), (x1, y0, W, y1)):
                    canvas.create_rectangle(bx0, by0, bx1, by1,
                                            fill=pal["dim"], outline="")
                # accent outline + corner ticks
                canvas.create_rectangle(x0, y0, x1, y1, outline=pal["accent"],
                                        width=3)
                t = 6
                for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                    canvas.create_oval(cx - t, cy - t, cx + t, cy + t,
                                       fill=pal["accent"], outline="")
                # name tag just above the box so the user always knows what
                # the spotlight is pointing at
                tag = self._target_label(step, target)
                if tag:
                    f = tkfont.Font(font=self.TAG_FONT)
                    tw = f.measure(tag) + 18
                    th = f.metrics("linespace") + 8
                    tx0 = max(2, min(W - tw - 2, (x0 + x1) // 2 - tw // 2))
                    ty0 = max(2, y0 - th - 6)
                    if ty0 < 2:
                        ty0 = y1 + 6
                    canvas.create_rectangle(tx0, ty0, tx0 + tw, ty0 + th,
                                            fill=pal["accent"], outline="")
                    canvas.create_text(tx0 + tw // 2, ty0 + th // 2,
                                       text=tag, fill="#000000",
                                       font=self.TAG_FONT)

        self._draw_card(W, H, pal, step, box)

    def _card_height(self, W, title, text):
        """Height the card needs so its body text never clips."""
        body_w = W - 2 * self.CARD_PAD - 90
        f_title = tkfont.Font(font=self.CARD_TITLE_FONT)
        f_body = tkfont.Font(font=self.CARD_BODY_FONT)
        # title is on a single line; count wrapped lines of the body text
        words = (text or "").split(" ")
        lines, cur = 1, 0
        for w in words:
            cur += f_body.measure(w) + f_body.measure(" ")
            if cur > body_w:
                lines += 1
                cur = f_body.measure(w) + f_body.measure(" ")
        body_h = lines * f_body.metrics("linespace")
        # header (title) + body + button row + paddings
        return (f_title.metrics("linespace") + 16 + body_h + 10 +
                34 + 24 + 14)

    def _draw_card(self, W, H, pal, step, box):
        """Draw the callout card (title + body text + Next/Back/Skip
        buttons) for the current step inside the overlay."""
        canvas = self._canvas
        if self._card is not None:
            try:
                self._card.destroy()
            except Exception:
                pass
        card = tk.Frame(canvas, bg=pal["panel"], bd=0, highlightthickness=1,
                        highlightbackground=pal["muted"])
        self._card = card

        tk.Label(card,
                 text="%d / %d    %s" % (self._idx + 1, len(self._steps),
                                         step.get("title", "")),
                 bg=pal["panel"], fg=pal["accent"],
                 font=self.CARD_TITLE_FONT, anchor="w").pack(
            fill="x", padx=self.CARD_PAD, pady=(14, 3))
        tk.Label(card, text=step.get("text", ""), bg=pal["panel"],
                 fg=pal["fg"], font=self.CARD_BODY_FONT, justify="left",
                 wraplength=W - 90, anchor="w").pack(
            fill="x", padx=self.CARD_PAD, pady=(0, 10))

        btns = tk.Frame(card, bg=pal["panel"])
        btns.pack(fill="x", padx=self.CARD_PAD, pady=(0, 12))
        tk.Button(btns, text="Skip tour", command=self._skip, bg=pal["panel"],
                  fg=pal["muted"], relief="flat", bd=0, font=self.CARD_BTN_FONT,
                  activebackground=pal["panel"],
                  activeforeground=pal["fg"]).pack(side="left")
        if self._idx > 0:
            tk.Button(btns, text="< Back", command=self._prev, bg=pal["panel"],
                      fg=pal["fg"], relief="flat", bd=0, font=self.CARD_BTN_FONT,
                      activebackground=pal["panel"]).pack(side="right",
                                                          padx=(0, 8))
        last = self._idx == len(self._steps) - 1
        tk.Button(btns, text="Finish" if last else "Next >",
                  command=self._skip if last else self._next,
                  bg=pal["accent"], fg="#000000", relief="flat", bd=0,
                  font=self.CARD_BTN_FONT,
                  activebackground=pal["accent"],
                  activeforeground="#000000").pack(side="right")

        cw = max(W - 40, 320)
        ch = self._card_height(W, step.get("title", ""),
                               step.get("text", ""))
        cx = W // 2
        cy = H - ch // 2 - 8
        canvas.create_window(cx, cy, window=card, width=cw, height=ch)

        # arrow from the card up to the spotlight box
        if box is not None:
            bx = (box[0] + box[2]) // 2
            by = box[3]
            tx = cx
            ty = cy - ch // 2
            if by < ty - 8:
                canvas.create_line(bx, by, tx, ty, fill=pal["accent"],
                                   width=3, arrow="last",
                                   arrowshape=(12, 14, 6))
