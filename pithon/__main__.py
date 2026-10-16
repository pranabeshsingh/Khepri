"""Entry point for ``python -m pithon``.

The console scripts declared in pyproject.toml (``khepri`` and ``pithon``) both
point at ``pithon.cli:main``. This module exists so the package is also usable
straight from a source checkout -- important because ``scripts/query_daemon.sh``
and the systemd units invoke the interpreter directly rather than relying on a
PATH entry that may not exist on a fresh Pi.
"""

import sys

from pithon.cli import main

if __name__ == "__main__":
    sys.exit(main())
