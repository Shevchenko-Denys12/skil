#!/usr/bin/env python3
"""Thin entry point for Pageviews fetching and caching."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikipedia_interest.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["fetch", *sys.argv[1:]]))
