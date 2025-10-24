#!/usr/bin/env python3
"""LRC CLI entry point."""

import sys

from .cli import main as cli_main


if __name__ == "__main__":
    sys.exit(cli_main())
