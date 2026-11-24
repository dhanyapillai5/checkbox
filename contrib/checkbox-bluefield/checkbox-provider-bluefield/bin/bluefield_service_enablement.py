#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert independently supplied service/timer enablement policy."""

import os
import re
import subprocess
import sys


def read_expectations(value):
    expected = {}
    for token in value.split():
        unit, separator, state = token.partition(":")
        if (
            not separator
            or not re.fullmatch(r"[A-Za-z0-9_@.-]+\.(service|timer)", unit)
            or unit.startswith("-")
            or state not in ("enabled", "disabled")
            or unit in expected
        ):
            raise ValueError(
                "Require unique unit.service|timer:enabled|disabled"
            )
        expected[unit] = state
    if not expected:
        raise ValueError("Supply BLUEFIELD_SERVICE_ENABLEMENT")
    return expected


def main():
    """Return 0 for matches, 1 for mismatches, or 2 for input/query errors."""
    try:
        expected = read_expectations(
            os.environ.get("BLUEFIELD_SERVICE_ENABLEMENT", "")
        )
        passed = True
        for unit, state in expected.items():
            print("Expected {}: {}".format(unit, state))
            result = subprocess.run(
                ["systemctl", "is-enabled", unit],
                capture_output=True,
                text=True,
                timeout=30,
                env=dict(os.environ, LC_ALL="C"),
            )
            print("Observed: " + repr(result.stdout))
            if result.stderr:
                print(result.stderr.rstrip(), file=sys.stderr)
            observed = result.stdout.strip()
            # A disabled observation normally has systemctl exit status 1.
            # SysV redirection diagnostics go to stderr; its state is stdout.
            good = observed == state and result.returncode == (
                0 if state == "enabled" else 1
            )
            passed &= good
            print(("PASS: " if good else "FAIL: ") + unit)
        return 0 if passed else 1
    except (
        OSError,
        UnicodeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
