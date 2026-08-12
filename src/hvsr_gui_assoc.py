"""
hvsr_gui_assoc.py
=================
Optional Windows file-association management for HVSR Analyzer.

The installer registers .eqd / .sg2 / .mseed / .miniseed at install time
(per-user HKCU\\Software\\Classes, removed on uninstall).  This module lets
the user turn those associations on or off from inside the app, so the
behaviour is never locked in by the installer.

All registry access uses the standard-library ``winreg`` module and every
write is scoped to HKCU - no admin rights are needed and the toggle can
always undo itself.  On non-Windows platforms the helpers degrade to
``assoc_enabled() == False`` and the GUI hides the toggle.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk

_EXTENSIONS = (".eqd", ".sg2", ".mseed", ".miniseed")
_PROGID = "HVSR_Analyzer"


def _base():
    return r"Software\Classes"


def _command():
    """The shell command that opens a dropped file with the app.

    Frozen build: the app exe itself.  Source run: pythonw + main.py
    (main.py puts its own folder on sys.path, so it finds hvsr_gui);
    pythonw is preferred so double-clicking a file never pops a console.
    """
    if getattr(sys, "frozen", False):
        return '"%s" "%%1"' % sys.executable
    here = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(here, "main.py")
    exe = sys.executable
    w = os.path.splitext(exe)[0] + "w.exe"
    if os.path.isfile(w):
        exe = w
    return '"%s" "%s" "%%1"' % (exe, main_py)


def _icon():
    """DefaultIcon value (None keeps the default Python icon on source runs)."""
    if getattr(sys, "frozen", False):
        return "%s,0" % sys.executable
    return None


def _reg():
    import winreg  # stdlib, Windows only
    return winreg


def assoc_enabled():
    """True when .mseed currently points at our ProgID in HKCU.

    Never raises: on non-Windows (where winreg is absent) it simply
    reports False, per the module contract."""
    try:
        wr = _reg()
        with wr.OpenKey(wr.HKEY_CURRENT_USER, r"%s\.mseed" % _base()) as key:
            val, _ = wr.QueryValueEx(key, "")
            return val == _PROGID
    except (OSError, ImportError):
        return False


def set_assoc(enabled):
    """Create (enabled) or remove (disabled) the HKCU file associations.

    The ProgID carries the open command and icon; each extension's
    default value points at that ProgID.  Everything lives under
    HKCU\\Software\\Classes so a normal user can toggle it freely.
    """
    wr = _reg()
    base = _base()
    if enabled:
        prog = r"%s\%s" % (base, _PROGID)
        with wr.CreateKey(wr.HKEY_CURRENT_USER,
                          prog + r"\shell\open\command") as key:
            wr.SetValueEx(key, "", 0, wr.REG_SZ, _command())
        icon = _icon()
        if icon:
            with wr.CreateKey(wr.HKEY_CURRENT_USER,
                              prog + r"\DefaultIcon") as key:
                wr.SetValueEx(key, "", 0, wr.REG_SZ, icon)
        for ext in _EXTENSIONS:
            with wr.CreateKey(wr.HKEY_CURRENT_USER, base + "\\" + ext) as key:
                wr.SetValueEx(key, "", 0, wr.REG_SZ, _PROGID)
    else:
        for ext in _EXTENSIONS:
            _delete_tree(wr, base + "\\" + ext)
        _delete_tree(wr, r"%s\%s" % (base, _PROGID))
    _notify_shell()


def _delete_tree(wr, subkey):
    """Recursively delete a key (winreg.DeleteTree needs Python 3.11+)."""
    children = []
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, subkey) as key:
            while True:
                try:
                    children.append(wr.EnumKey(key, len(children)))
                except OSError:
                    break
    except OSError:
        return
    for child in children:
        _delete_tree(wr, subkey + "\\" + child)
    try:
        wr.DeleteKey(wr.HKEY_CURRENT_USER, subkey)
    except OSError:
        pass


def _notify_shell():
    """Ask Explorer to refresh its association cache immediately."""
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:  # noqa: BLE001  (best-effort refresh only)
        pass


class HVSRAppAssocMixin:
    """GUI toggle for the file associations (page 4, Windows only)."""

    def _build_assoc_toggle(self, parent, row):
        """Build the File Associations card; returns the frame."""
        f = self._card(parent, "File Associations", row)
        self._vars["file_assoc"] = tk.BooleanVar(value=assoc_enabled())
        ttk.Checkbutton(
            f,
            text="OPEN .eqd/.sg2/.mseed/.miniseed BY DOUBLE-CLICK",
            variable=self._vars["file_assoc"],
            command=self._toggle_file_assoc,
            style="Card.TCheckbutton").pack(anchor="w")
        ttk.Label(
            f,
            text="Double-clicking a recording opens this app with it "
                 "pre-loaded (per-user setting, removed when unchecked).",
            style="Card.TLabel").pack(anchor="w", pady=(4, 0))
        return f

    def _toggle_file_assoc(self):
        """Checkbox handler: register / unregister the associations."""
        on = self._vars["file_assoc"].get()
        try:
            set_assoc(on)
        except Exception as exc:  # noqa: BLE001
            self._log_line("SYS_ERR: could not %s file associations: %s"
                           % ("enable" if on else "disable", exc))
            self._vars["file_assoc"].set(not on)
            return
        self._log_line("SYS: File associations %s - double-click a recording "
                       "to open it."
                       % ("ENABLED" if on else "DISABLED"))
