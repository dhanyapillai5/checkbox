#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert independently supplied boot arguments against /proc/cmdline."""

import os
from pathlib import Path
import sys


def read_arguments(value):
    arguments = value.split()
    if len(set(arguments)) != len(arguments) or any(
        not all(char.isprintable() for char in arg) or arg == "--"
        for arg in arguments
    ):
        raise ValueError(
            "Require unique printable argument tokens, excluding --"
        )
    return set(arguments)


def main():
    """Return 0 for matches, 1 for mismatches, or 2 for input/read errors."""
    try:
        required = read_arguments(
            os.environ.get("BLUEFIELD_REQUIRED_BOOT_ARGS", "")
        )
        forbidden = read_arguments(
            os.environ.get("BLUEFIELD_FORBIDDEN_BOOT_ARGS", "")
        )
        if not required:
            raise ValueError("Supply BLUEFIELD_REQUIRED_BOOT_ARGS")
        if required & forbidden:
            raise ValueError("Required and forbidden arguments overlap")
        print("Required arguments: " + " ".join(sorted(required)))
        print("Forbidden arguments: " + " ".join(sorted(forbidden)))
        text = Path("/proc/cmdline").read_text()
        print("Observed /proc/cmdline: " + repr(text))
        if not text.strip() or len(text.splitlines()) != 1:
            raise ValueError("Empty or multiline kernel command line")
        # Tokens after -- are init arguments, not kernel parameters.
        tokens = text.split()
        actual = set(
            tokens[: tokens.index("--")] if "--" in tokens else tokens
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2

    failed = False
    for arg in sorted(required):
        good = arg in actual
        failed |= not good
        print(("PASS: required present " if good else "FAIL: missing ") + arg)
    for arg in sorted(forbidden):
        good = arg not in actual
        failed |= not good
        print(
            ("PASS: forbidden absent " if good else "FAIL: forbidden present ")
            + arg
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
