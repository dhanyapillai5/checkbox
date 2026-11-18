#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert the running kernel release against an explicit expectation."""

import os
import platform
import sys


def main():
    """Fail on missing/invalid input or a different running release."""
    expected = os.environ.get("BLUEFIELD_EXPECTED_KERNEL", "")
    if not expected or any(char.isspace() for char in expected):
        print(
            "FAIL: BLUEFIELD_EXPECTED_KERNEL must contain one nonempty "
            "kernel release without whitespace.",
            file=sys.stderr,
        )
        return 2

    actual = platform.release()
    print("Expected kernel: {}".format(expected))
    print("Running kernel: {}".format(actual))
    if actual != expected:
        print("FAIL: running kernel does not match the expectation.")
        return 1
    print("PASS: running kernel matches the expectation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
