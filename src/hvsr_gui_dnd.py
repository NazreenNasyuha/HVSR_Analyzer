"""
hvsr_gui_dnd.py
===============
Optional drag-and-drop support for the HVSR Analyzer window.

Tkinter cannot accept OS-level file drops with the standard library
alone; the small third-party package ``tkinterdnd2`` (which ships the
native ``tkdnd`` library for Windows) makes it possible.  When the
package is installed - it is bundled into the packaged exe by
``build_exe.py`` via ``--collect-all tkinterdnd2`` - the whole window
becomes a drop target and dropped files are routed straight into the
Z / N / E input slots.  Without the package the GUI behaves exactly as
before; drag & drop is simply not registered.

This module exposes three things:

- ``DND_AVAILABLE`` : True when tkinterdnd2 imported cleanly,
- ``TK_BASE``      : the ``TkinterDnD.Tk`` root class (or None), so
  hvsr_gui.py can pick the Tk base class at class-definition time,
- ``HVSRAppDndMixin`` : the window wiring mixed into ``HVSRApp``.

A dropped *trio* of component files (miniSEED or text) is assigned to
the Z / N / E slots with ``assign_components`` (the same helper the
loaders use); a single dropped file goes into the Z slot, exactly like
the Z Browse button.
"""

import os

import hvsr_theme
from hvsr_io_data import DataError, assign_components

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
    TK_BASE = TkinterDnD.Tk
except Exception:
    # tkinterdnd2 missing (source install without it, exotic Tk build, ...):
    # fall back to a plain Tk root and skip drop-target registration.
    DND_AVAILABLE = False
    TK_BASE = None

# NOTE for future developers: the guard above covers a missing/broken
# tkinterdnd2 *import*, not a TkinterDnD.Tk() *construction* failure (e.g. a
# tkdnd tcl package that cannot load).  The shipped exe bundles tkdnd via
# --collect-all, so construction is safe there; a source install with a
# half-broken tkinterdnd2 would raise inside HVSRApp.__init__ and surface
# through main.py's startup-error reporter.  That single spot is the known,
# accepted fragility of the optional-dependency design.


class HVSRAppDndMixin:
    def _register_drop_target(self):
        """Make the window (and every widget in it) accept dropped files.

        tkdnd delivers a drop to the widget under the pointer, so a drop
        landing on any entry, button or notebook tab is caught as long as
        that widget registered itself.  A no-op when tkinterdnd2 is not
        available.
        """
        if not DND_AVAILABLE:
            return
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_drop)
        self.dnd_bind("<<DropEnter>>", lambda e: self._highlight_hint(True))
        self.dnd_bind("<<DropLeave>>", lambda e: self._highlight_hint(False))
        for w in _iter_widgets(self):
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
                w.dnd_bind("<<DropEnter>>", lambda e: self._highlight_hint(True))
                w.dnd_bind("<<DropLeave>>", lambda e: self._highlight_hint(False))
            except Exception:
                # some exotic widgets refuse registration; the root window
                # registration above still covers those areas
                pass

    def _dropped_paths(self, event):
        """Parse tkdnd's event.data into a list of existing paths.

        Both files and folders survive this filter; _on_drop decides what
        to do with them.  tkdnd quotes paths containing spaces with curly
        braces.  Tcl's splitlist decodes that syntax, but an *unbraced*
        Windows path (for example C: backslash Users backslash ...) would
        have its backslash escapes interpreted (newline, bell, ...), so
        backslashes are normalised to forward slashes first, then each
        parsed path is converted back to the native form.
        """
        raw = (event.data or "").replace("\\", "/")
        paths = []
        for p in list(self.tk.splitlist(raw)):
            native = os.path.normpath(p)
            if os.path.exists(native):
                paths.append(native)
        return paths

    def _on_drop(self, event):
        """Route dropped files/folders (runs on the UI thread).

        A single dropped folder starts a batch run on it; dropped files
        follow the 1-file / Z-N-E-trio rules of _mount_cli.
        """
        items = self._dropped_paths(event)
        folders = [p for p in items if os.path.isdir(p)]
        files = [p for p in items if os.path.isfile(p)]
        if folders:
            if len(folders) == 1 and not files:
                self._log_line("SYS: Batch folder dropped - "
                               "BATCH PROCESSING...")
                self._run_batch(folders[0])
            else:
                self._log_line("SYS_ERR: drop a single folder (or only data "
                               "files) - not a mix of both")
            return
        if not files:
            self._log_line("SYS_ERR: drop data files (.eqd/.sg2/3-column, or "
                           "a Z/N/E trio of component files)")
            return
        self._mount_cli(files)

    def _mount_cli(self, paths):
        """Mount files given on the command line (file associations) or
        dropped onto the window: one file, or a Z/N/E trio."""
        try:
            if len(paths) == 1:
                if paths[0].lower().endswith(".pz"):
                    self._mount_response(paths[0])
                else:
                    self._mount_single(paths[0])
            else:
                if any(p.lower().endswith(".pz") for p in paths):
                    # a .pz is not a signal component; dropping it among
                    # several files would misroute it into a Z/N/E slot
                    self._log_line("SYS_ERR: drop the .pz response file on "
                                   "its own - it is not a signal component")
                    return
                if len(paths) == 3:
                    self._mount_trio(paths)
                else:
                    self._log_line("SYS_ERR: got %d files - pick a single "
                                   "3-column/.eqd/.sg2 file or a Z, N, E trio "
                                   "of component files" % len(paths))
        except DataError as exc:
            self._log_line("SYS_ERR: " + str(exc))

    def _mount_response(self, path):
        """Drop / command-line .pz: fill the instrument-response slot."""
        self._vars["pz_entry"].delete(0, "end")
        self._vars["pz_entry"].insert(0, path)
        self._log_line("SYS: Instrument response (.pz) mounted: "
                       + os.path.basename(path))

    def _highlight_hint(self, on):
        """Strong drop feedback while a drag hovers over the window: tint
        the whole input card to the theme's hover colour, swap the banner
        text to a release prompt and paint it in the accent colour."""
        theme = hvsr_theme.current
        hint = getattr(self, "_drop_hint", None)
        if hint is not None:
            hint.configure(
                foreground=theme["ACCENT"] if on else theme["TEXT_MUTED"],
                text=("\u25bc RELEASE TO LOAD" if on
                      else getattr(self, "_drop_hint_base", "")))
        card = getattr(self, "_drop_card", None)
        if card is not None:
            # ttk frames have no background option; switch to the dedicated
            # hover style (refreshed with the theme on every switch)
            card.configure(style="CardHover.TFrame" if on else "Card.TFrame")

    def _mount_single(self, path):
        """Drop of one file: fill the Z slot, clear N / E (mirrors _browse)."""
        self._vars["z_entry"].delete(0, "end")
        self._vars["z_entry"].insert(0, path)
        for slot in ("n", "e"):
            self._vars[slot + "_entry"].delete(0, "end")
        ext = os.path.splitext(path)[1].lower()
        if ext == ".eqd":
            self._log_line("SYS: Single .eqd file provides all 3 components.")
        elif ext == ".sg2":
            self._log_line("SYS: Single .sg2 file holds all 3 components "
                           "(Z/N/E detected automatically).")
        else:
            self._log_line("SYS: Dropped " + os.path.basename(path))
        self._refresh_preview()

    def _mount_trio(self, paths):
        """Drop of three files: assign to Z / N / E and mount them."""
        mapping = assign_components(paths)
        exts = {os.path.splitext(mapping[c])[1].lower() for c in "ZNE"}
        # reject the confusing mixes up front so the user gets a clear
        # message instead of a silently empty preview afterwards
        if exts & {".eqd", ".sg2"}:
            raise DataError(
                "a single .eqd/.sg2 file already holds all 3 components - "
                "drop it on its own")
        mseed_exts = {".mseed", ".miniseed"}
        if exts & mseed_exts and not exts <= mseed_exts:
            raise DataError(
                "the 3 dropped files mix binary miniSEED with text files - "
                "select either 3 miniSEED files or 3 text files")
        for c in "ZNE":
            w = self._vars[c.lower() + "_entry"]
            w.delete(0, "end")
            w.insert(0, mapping[c])
        self._log_line("SYS: Dropped 3 component files (Z: %s, N: %s, E: %s)"
                       % (os.path.basename(mapping["Z"]),
                          os.path.basename(mapping["N"]),
                          os.path.basename(mapping["E"])))
        self._refresh_preview()


def _iter_widgets(root):
    """Yield a widget and all of its descendants (depth-first)."""
    stack = [root]
    while stack:
        w = stack.pop()
        yield w
        stack.extend(w.winfo_children())
