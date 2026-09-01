"""PyInstaller's Analysis entry script.

Imports `inductor_designer.ui.main` as an ordinary package module and calls
it, rather than making `ui/main.py` itself the Analysis script (which would
freeze it under the synthetic `__main__` name instead of its real one). This
mirrors exactly what the `inductor-designer` console script in
`pyproject.toml` already does for a `pip install`, so the frozen build and
an installed wheel run the same code the same way.
"""

from __future__ import annotations

import sys

from inductor_designer.ui.main import main

if __name__ == "__main__":
    sys.exit(main())
