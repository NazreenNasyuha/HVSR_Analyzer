"""
main.py
=======
Entry point for the HVSR Analyzer GUI.

Run with:  python main.py
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _report_startup_failure(exc):
    """Surface startup errors instead of failing silently under pythonw.

    pythonw launches without a console, so an unhandled exception is
    invisible to the user.  Show a message box when possible and always
    write the traceback to %LOCALAPPDATA%/HVSR_Analyzer_startup_error.log.
    """
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    # Write the log first so it exists even if the message box cannot be shown.
    try:
        log_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        log_path = os.path.join(log_dir, "HVSR_Analyzer_startup_error.log")
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(trace)
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "HVSR Analyzer - Startup Error",
            "HVSR Analyzer could not start:" + "\n\n%s\n\n%s"
            % (type(exc).__name__ + ": " + str(exc), trace))
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        from hvsr_gui import main
        main()
    except Exception as exc:
        _report_startup_failure(exc)
        sys.exit(1)
