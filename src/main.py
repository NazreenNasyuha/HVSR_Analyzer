"""
main.py
=======
Entry point for the HVSR Analyzer GUI.

Run with:  python main.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from hvsr_gui import main

if __name__ == "__main__":
    main()
