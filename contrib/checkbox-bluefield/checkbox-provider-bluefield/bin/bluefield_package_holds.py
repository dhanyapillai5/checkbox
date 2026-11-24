#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert a candidate's required package-hold subset without changing APT."""

import os
import re
import subprocess
import sys


def read_names(text, allow_architecture=False):
    names = text.split()
    pattern = r"[a-z0-9][a-z0-9+.-]+"
    if allow_architecture:
        pattern += r"(?::[a-z0-9][a-z0-9-]*)?"
    if len(set(names)) != len(names) or any(
        not re.fullmatch(pattern, name) for name in names
    ):
        raise ValueError("Package names must be valid and unique")
    return set(names)


def main():
    """Return 0 on matches, 1 on missing holds, or 2 on input/query errors."""
    try:
        required = read_names(os.environ.get("BLUEFIELD_REQUIRED_HOLDS", ""))
        if not required:
            raise ValueError("Supply BLUEFIELD_REQUIRED_HOLDS")
        print("Required holds: " + " ".join(sorted(required)))
        result = subprocess.run(
            ["apt-mark", "showhold"],
            capture_output=True,
            text=True,
            timeout=30,
            env=dict(os.environ, LC_ALL="C"),
        )
        print("Observed holds:\n" + result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode:
            raise ValueError("apt-mark showhold failed")
        actual = read_names(result.stdout, allow_architecture=True)
    except (
        OSError,
        UnicodeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2

    missing = required - actual
    for name in sorted(required):
        print(
            "FAIL: {} is not held".format(name)
            if name in missing
            else "PASS: {} is held".format(name)
        )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
