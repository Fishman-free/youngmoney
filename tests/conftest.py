"""Path setup so the shared test helper (`synth`) imports under pytest too.

unittest discover puts `tests/` on sys.path implicitly; pytest does not, which
broke collection with ModuleNotFoundError: No module named 'synth'.
"""

import os
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
for p in (TESTS, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
