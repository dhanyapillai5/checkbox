#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Read-only assertions for candidate file removals and release suffix."""

import argparse
import os
from pathlib import Path
import sys


def check_absent(value):
    paths = value.split()
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("Supply unique paths in BLUEFIELD_ABSENT_FILES")
    for path in paths:
        parsed = Path(path)
        if (
            not parsed.is_absolute()
            or str(parsed) != path
            or ".." in parsed.parts
            or path == "/"
        ):
            raise ValueError("Require normalized absolute file paths: " + path)
    passed = True
    for path in paths:
        print("Expected absent: " + path)
        try:
            Path(path).lstat()
        except FileNotFoundError:
            print("PASS: absent " + path)
        else:
            print("FAIL: present " + path)
            passed = False
    return 0 if passed else 1


def check_release(suffix):
    if (
        not suffix.startswith("_")
        or len(suffix) < 2
        or any(char.isspace() or not char.isprintable() for char in suffix)
    ):
        raise ValueError("Supply BLUEFIELD_EXPECTED_RELEASE_SUFFIX starting _")
    print("Expected /etc/mlnx-release suffix: " + suffix)
    text = Path("/etc/mlnx-release").read_text()
    print("Observed /etc/mlnx-release: " + repr(text))
    lines = text.splitlines()
    good = (
        len(lines) == 1
        and len(lines[0]) > len(suffix)
        and all(char.isprintable() and not char.isspace() for char in lines[0])
        and lines[0].endswith(suffix)
    )
    print(
        "PASS: release suffix matches"
        if good
        else "FAIL: invalid release marker or suffix mismatch"
    )
    return 0 if good else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=("absent", "release"))
    args = parser.parse_args(argv)
    try:
        if args.check == "absent":
            return check_absent(os.environ.get("BLUEFIELD_ABSENT_FILES", ""))
        return check_release(
            os.environ.get("BLUEFIELD_EXPECTED_RELEASE_SUFFIX", "")
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
