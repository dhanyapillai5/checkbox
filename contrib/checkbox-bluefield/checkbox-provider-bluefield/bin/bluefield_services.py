#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert requested systemd states without restarting services."""

import os
import re
import subprocess
import sys


def read_expectations(value):
    expected = {}
    for item in value.split():
        fields = item.split(":")
        if (
            len(fields) != 3
            or not re.fullmatch(r"[A-Za-z0-9_@.-]+\.service", fields[0])
            or fields[1] != "active"
            or fields[2] not in ("running", "exited")
            or fields[0] in expected
        ):
            raise ValueError(
                "Require unique unit.service:active:running|exited"
            )
        expected[fields[0]] = tuple(fields[1:])
    if not expected:
        raise ValueError("Supply BLUEFIELD_REQUIRED_SERVICES")
    return expected


def check(expected):
    passed = True
    for unit, states in expected.items():
        result = subprocess.run(
            [
                "systemctl",
                "show",
                unit,
                "--no-pager",
                "-p",
                "LoadState",
                "-p",
                "ActiveState",
                "-p",
                "SubState",
                "-p",
                "Result",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=dict(os.environ, LC_ALL="C"),
        )
        print("Expected {}: loaded {} {} success".format(unit, *states))
        print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode:
            raise ValueError("Unable to query required service: " + unit)
        fields = {}
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if not separator or key in fields:
                raise ValueError("Invalid service observation")
            fields[key] = value
        actual = tuple(
            fields.get(k)
            for k in (
                "LoadState",
                "ActiveState",
                "SubState",
                "Result",
            )
        )
        good = actual == ("loaded", *states, "success")
        print(("PASS: " if good else "FAIL: ") + unit)
        passed &= good
    return 0 if passed else 1


def main():
    try:
        return check(
            read_expectations(
                os.environ.get("BLUEFIELD_REQUIRED_SERVICES", "")
            )
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
