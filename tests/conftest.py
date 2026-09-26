"""Pytest bootstrap for linprocman core-module tests.

Puts ``src/`` and ``src/modules/`` on ``sys.path`` so the pure core modules
(``procfs``, ``sysfs``) import standalone — without triggering the GTK-side
package ``__init__`` files. Tests run entirely against the fixture trees under
``tests/fixtures/``; they never read the live kernel.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
SRC_MODULES = os.path.join(SRC, "modules")

for _path in (SRC, SRC_MODULES):
    if _path not in sys.path:
        sys.path.insert(0, _path)
