#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Compare literal configuration assignments with independent policy inputs."""

import json
import os
from pathlib import Path
import re
import shlex
import sys


def read_expectations(text):
    expected = json.loads(text)
    if not isinstance(expected, list) or not expected:
        raise ValueError("Require a nonempty list of file/key/value objects")
    seen = set()
    for item in expected:
        if (
            not isinstance(item, dict)
            or set(item) != {"file", "key", "value"}
            or not all(isinstance(value, str) for value in item.values())
        ):
            raise ValueError("Require string file/key/value fields")
        path = Path(item["file"])
        identity = (item["file"], item["key"])
        if (
            not path.is_absolute()
            or str(path) != item["file"]
            or ".." in path.parts
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item["key"])
            or identity in seen
        ):
            raise ValueError("Invalid or duplicate configuration expectation")
        seen.add(identity)
    return expected


def read_setting(text, key):
    values = []
    for line in text.splitlines():
        if re.match(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=", line):
            # Parse literal assignments only: no shell sourcing or expansion.
            value = line.split("=", 1)[1].strip()
            if any(char in value for char in ("$", "`", ";", "\\")):
                raise ValueError(
                    "Unsupported nonliteral assignment for " + key
                )
            tokens = shlex.split(value, comments=True, posix=True)
            if len(tokens) > 1:
                raise ValueError("Invalid literal assignment for " + key)
            values.append(tokens[0] if tokens else "")
    if len(values) > 1:
        raise ValueError("Duplicate assignment for " + key)
    return values[0] if values else None


def main():
    """Return 0 for matches, 1 for mismatches, or 2 for input/read errors."""
    try:
        reference = os.environ.get("BLUEFIELD_EXPECTED_SETTINGS", "")
        if not reference or not Path(reference).is_absolute():
            raise ValueError("Supply absolute BLUEFIELD_EXPECTED_SETTINGS")
        expected = read_expectations(Path(reference).read_text())
        print("Candidate settings reference: " + reference)
        passed = True
        for item in expected:
            path, key, value = (
                item[name] for name in ("file", "key", "value")
            )
            print("Expected {}: {}={!r}".format(path, key, value))
            actual = read_setting(Path(path).read_text(), key)
            print("Observed {}: {}={!r}".format(path, key, actual))
            good = actual == value
            passed &= good
            print(("PASS: " if good else "FAIL: ") + path + ":" + key)
        return 0 if passed else 1
    except (OSError, UnicodeError, ValueError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
