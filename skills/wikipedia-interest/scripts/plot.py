#!/usr/bin/env python3
"""Thin entry point for a chart from analyzed JSON."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikipedia_interest.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["plot", *sys.argv[1:]]))
