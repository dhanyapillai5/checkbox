#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Discover DPU management interfaces by device driver relationships."""

import json
import os
from pathlib import Path
import re
import sys


def read_expectations(source):
    """Read management roles and their device/parent driver identities."""
    expected = json.loads(Path(source).read_text())
    if not isinstance(expected, dict) or not expected:
        raise ValueError("Expected a nonempty JSON object of management roles")
    for role, identity in expected.items():
        if not role or not isinstance(identity, dict):
            raise ValueError("Each named role must contain a driver identity")
        if set(identity) not in ({"driver"}, {"driver", "parent_driver"}):
            raise ValueError("Supply driver and optional parent_driver only")
        if any(
            not isinstance(value, str)
            or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value)
            for value in identity.values()
        ):
            raise ValueError("Invalid driver identity")
    return expected


def driver_name(device):
    """Read a bound driver name, allowing devices without driver bindings."""
    try:
        return (device / "driver").readlink().name
    except FileNotFoundError:
        return None


def check_interfaces(expected, root=Path("/sys/class/net")):
    """Require unique distinct interfaces and report their discovered names."""
    observed = {}
    for interface in sorted(root.iterdir()):
        try:
            device = (interface / "device").resolve(strict=True)
        except FileNotFoundError:
            # Software interfaces such as loopback have no backing device.
            if not (interface / "device").is_symlink():
                continue
            raise
        observed[interface.name] = {
            "driver": driver_name(device),
            "parent_driver": driver_name(device.parent),
        }

    failed = False
    used = set()
    for role, identity in expected.items():
        print(
            "Expected {}: {}".format(
                role, json.dumps(identity, sort_keys=True)
            )
        )
        matches = [
            name
            for name, actual in observed.items()
            if all(actual[key] == value for key, value in identity.items())
        ]
        if len(matches) != 1:
            print(
                "FAIL: {} expected one interface; found {} ({})".format(
                    role, len(matches), ", ".join(matches)
                )
            )
            failed = True
            continue
        name = matches[0]
        print(
            "Observed {}: interface {}; {}".format(
                role, name, json.dumps(observed[name], sort_keys=True)
            )
        )
        if name in used:
            print("FAIL: interface {} matched more than one role".format(name))
            failed = True
        else:
            print("PASS: {} interface {} is present".format(role, name))
            used.add(name)
    return 1 if failed else 0


def main():
    """Return 0 for matches, 1 for missing/ambiguous roles, 2 for errors."""
    try:
        source = os.environ.get("BLUEFIELD_EXPECTED_MANAGEMENT", "")
        if not source:
            raise ValueError("Supply BLUEFIELD_EXPECTED_MANAGEMENT JSON file")
        expected = read_expectations(source)
        print("Management expectations: " + source)
        return check_interfaces(expected)
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
