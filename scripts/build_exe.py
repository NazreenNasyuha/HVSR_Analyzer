"""
build_exe.py
============
Build a standalone Windows executable with PyInstaller.

The resulting exe bundles the application together with a *private* Python
runtime and tkinter, so end users do **not** need to install Python to run
HVSR Analyzer.

Run from the project root:

    pip install pyinstaller
    python scripts/build_exe.py

Output:  dist/HVSR_Analyzer/            (the folder the Inno Setup installer
                                         bundles; see installer/README notes in
                                         installer/HVSR_Analyzer_Setup.iss)
         build/                         (PyInstaller work dir, safe to delete)

Why --onedir instead of --onefile?
  - The app spawns multiprocessing workers (ProcessPoolExecutor) for the
    auto-tune sweep and the 1D inversion.  A folder layout lets those workers
    relaunch the exe in place, which is faster and more robust than the
    one-file mode's extract-to-temp behaviour.
  - Faster startup and fewer antivirus false positives than onefile.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    os.chdir(ROOT)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed.\n"
              "Install it with:  pip install pyinstaller")
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",        # overwrite previous build without asking
        "--clean",            # purge caches for a reproducible build
        "--noconsole",        # GUI application: no console window
        "--onedir",           # folder layout (see module docstring)
        "--name", "HVSR_Analyzer",
        # Absolute path: PyInstaller resolves --icon (and other file args in
        # the spec) relative to the spec directory, not the working directory.
        "--icon", os.path.join(ROOT, "installer", "HVSR_Analyzer.ico"),
        # Drag & drop uses the optional tkinterdnd2 package; --collect-all
        # bundles it together with its native tkdnd binaries (the installer
        # build always ships it, so end users get drag & drop out of the box).
        "--collect-all", "tkinterdnd2",
        "--specpath", os.path.join("build", "spec"),
        "--distpath", "dist",
        "--workpath", os.path.join("build", "pyinstaller"),
        os.path.join(ROOT, "src", "main.py"),
    ]

    print("Building standalone app (this bundles a private Python runtime):")
    print("  " + " ".join(cmd))
    print()
    rc = subprocess.call(cmd)
    if rc == 0:
        exe = os.path.join("dist", "HVSR_Analyzer", "HVSR_Analyzer.exe")
        print("\nDone.  The packaged app is at:  %s" % exe)
        print("Compile the installer with Inno Setup 6 (ISCC.exe "
              "installer\\HVSR_Analyzer_Setup.iss) to ship it to end users.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
