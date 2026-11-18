#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert explicitly required modules are loaded without loading them."""

import os
from pathlib import Path
import re
import sys


def main():
    """Return 0 for loaded modules, 1 for missing ones, 2 for input errors."""
    required = os.environ.get("BLUEFIELD_REQUIRED_MODULES", "").split()
    if not required or any(
        not re.fullmatch(r"[A-Za-z0-9_]+", name) for name in required
    ):
        print(
            "FAIL: BLUEFIELD_REQUIRED_MODULES must contain module names "
            "separated by whitespace, using underscores rather than hyphens.",
            file=sys.stderr,
        )
        return 2

    try:
        loaded = {
            line.split()[0]
            for line in Path("/proc/modules").read_text().splitlines()
            if line.strip()
        }
    except (OSError, UnicodeError) as exc:
        print(
            "FAIL: cannot read /proc/modules: {}".format(exc), file=sys.stderr
        )
        return 2

    missing = False
    for name in dict.fromkeys(required):
        if name in loaded:
            print("PASS: required module {} is loaded".format(name))
        else:
            print("FAIL: required module {} is not loaded".format(name))
            missing = True
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
