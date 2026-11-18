#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Compare required installed packages with the candidate inventory."""

import csv
import io
import os
from pathlib import Path
import re
import subprocess
import sys


def read_inventory(text, with_status=False):
    """Read package/version/architecture TSV, optionally with dpkg status."""
    packages = {}
    for row in csv.reader(io.StringIO(text), delimiter="\t"):
        if len(row) != (4 if with_status else 3) or not all(row):
            raise ValueError("Invalid package inventory row: {!r}".format(row))
        name, version, architecture = row[:3]
        if any(char.isspace() for field in row[:3] for char in field):
            raise ValueError("Whitespace in package inventory fields")
        key = (name, architecture)
        if key in packages:
            raise ValueError(
                "Duplicate package inventory entry: {}".format(key)
            )
        packages[key] = (version, row[3] if with_status else "installed")
    if not packages:
        raise ValueError("Empty package inventory")
    return packages


def main():
    """Return 0 for matches, 1 for mismatches, and 2 for input/query errors."""
    inventory = os.environ.get("BLUEFIELD_CANDIDATE_INVENTORY", "")
    required = os.environ.get("BLUEFIELD_REQUIRED_PACKAGES", "").split()
    try:
        if not inventory or not required:
            raise ValueError(
                "Supply BLUEFIELD_CANDIDATE_INVENTORY and "
                "BLUEFIELD_REQUIRED_PACKAGES"
            )
        if len(set(required)) != len(required) or any(
            not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", name)
            for name in required
        ):
            raise ValueError("Required package names must be valid and unique")
        candidate = read_inventory(Path(inventory).read_text())
        expected = {}
        for name in required:
            matches = [key for key in candidate if key[0] == name]
            if len(matches) != 1:
                raise ValueError(
                    "Required package missing or ambiguous in candidate: "
                    + name
                )
            key = matches[0]
            expected[key] = candidate[key][0]

        result = subprocess.run(
            [
                "dpkg-query",
                "-W",
                "-f=${Package}\t${Version}\t${Architecture}"
                "\t${db:Status-Status}\n",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            env=dict(os.environ, LC_ALL="C"),
        )
        actual = read_inventory(result.stdout, with_status=True)
    except (
        OSError,
        UnicodeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2

    print("Candidate inventory: {}".format(inventory))
    failed = False
    for (name, architecture), version in expected.items():
        observed = actual.get((name, architecture))
        print(
            "Expected: {} {} {} installed".format(name, version, architecture)
        )
        if observed != (version, "installed"):
            failed = True
            observations = [
                "{} {} {} {}".format(n, v, a, status)
                for (n, a), (v, status) in actual.items()
                if n == name
            ]
            print(
                "FAIL: observed "
                + ("; ".join(observations) or name + " missing")
            )
        else:
            print("PASS: {} matches the candidate".format(name))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
