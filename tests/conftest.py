"""Pytest configuration — adds tool directories to sys.path."""

import os
import sys

_base = os.path.join(os.path.dirname(__file__), "..")

for subdir in ("skills/bibtidy/tools", "tests"):
    d = os.path.abspath(os.path.join(_base, subdir))
    if d not in sys.path:
        sys.path.insert(0, d)
