#!/usr/bin/env python3
"""Repository entry point for `python main.py`."""

import sys
from pathlib import Path

# Allow running from repository root without installing the package first.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from gentooinstall.main import main

if __name__ == '__main__':
	raise SystemExit(main())
