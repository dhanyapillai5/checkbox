#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Compare installed Conflicts fields with independent candidate metadata."""

import os
from pathlib import Path
import re
import subprocess
import sys


def read_metadata(text, with_status=False):
    packages = {}
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) != (3 if with_status else 2):
            raise ValueError("Invalid Conflicts TSV row: {!r}".format(line))
        name, conflicts = fields[:2]
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", name)
            or name in packages
            or conflicts != conflicts.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in conflicts)
            or (not with_status and not conflicts)
            or (with_status and not fields[2])
        ):
            raise ValueError("Invalid or duplicate Conflicts entry: " + name)
        packages[name] = (
            conflicts,
            fields[2] if with_status else "installed",
        )
    if not packages:
        raise ValueError("Empty Conflicts metadata")
    return packages


def main():
    """Return 0 for matches, 1 for mismatches, and 2 for input/query errors."""
    reference = os.environ.get("BLUEFIELD_EXPECTED_CONFLICTS", "")
    try:
        if not reference or not Path(reference).is_absolute():
            raise ValueError("Supply absolute BLUEFIELD_EXPECTED_CONFLICTS")
        expected = read_metadata(Path(reference).read_text())
        print("Candidate Conflicts reference: " + reference)
        for name, (conflicts, _) in expected.items():
            print("Expected {}: Conflicts: {}".format(name, conflicts))
        result = subprocess.run(
            [
                "dpkg-query",
                "-W",
                "-f=${Package}\t${Conflicts}\t${db:Status-Status}\n",
                *expected,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=dict(os.environ, LC_ALL="C"),
        )
        print("Observed package/Conflicts/status:\n" + result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode:
            raise ValueError("dpkg-query failed for required packages")
        actual = read_metadata(result.stdout, with_status=True)
    except (
        OSError,
        UnicodeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2

    failed = False
    for name, metadata in expected.items():
        good = actual.get(name) == metadata
        failed |= not good
        print(
            ("PASS: " if good else "FAIL: ")
            + name
            + " installed Conflicts "
            + ("matches" if good else "missing or mismatched")
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
