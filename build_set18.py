#!/usr/bin/env python3
"""Compatibility entry point for the Set 18 data build."""
import sys

from build_set import main


if __name__ == "__main__":
    main(["--set", "18", *sys.argv[1:]])
