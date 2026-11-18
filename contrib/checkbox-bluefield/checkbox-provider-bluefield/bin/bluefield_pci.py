#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert expected DPU PCI identities and driver bindings using sysfs."""

import csv
import os
from pathlib import Path
import re
import sys


def read_expectations(path):
    """Read headerless address/vendor/device/driver TSV expectations."""
    expected = {}
    with Path(path).open(newline="") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            if len(row) != 4:
                raise ValueError("Expected four tab-separated PCI fields")
            address, vendor, device, driver = row
            if (
                not re.fullmatch(
                    r"[0-9a-f]{4}:[0-9a-f]{2}:[01][0-9a-f]\.[0-7]", address
                )
                or not re.fullmatch(r"[0-9a-f]{4}", vendor)
                or not re.fullmatch(r"[0-9a-f]{4}", device)
                or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", driver)
            ):
                raise ValueError("Invalid PCI expectation: {!r}".format(row))
            if address in expected:
                raise ValueError("Duplicate PCI address: " + address)
            expected[address] = (vendor, device, driver)
    if not expected:
        raise ValueError("Empty PCI expectations")
    return expected


def check_devices(expected, root=Path("/sys/bus/pci/devices")):
    """Report all identity/binding mismatches; allow additional PCI devices."""
    # An inaccessible/missing PCI subsystem is an observation error.
    available = {path.name for path in root.iterdir()}
    failed = False
    for address, identity in expected.items():
        print("Expected: {} {} {} {}".format(address, *identity))
        if address not in available:
            print("FAIL: PCI device {} is missing".format(address))
            failed = True
            continue
        path = root / address
        vendor = path.joinpath("vendor").read_text().strip().removeprefix("0x")
        device = path.joinpath("device").read_text().strip().removeprefix("0x")
        try:
            driver = path.joinpath("driver").readlink().name
        except FileNotFoundError:
            driver = "unbound"
        actual = (vendor, device, driver)
        print("Observed: {} {} {} {}".format(address, *actual))
        if actual == identity:
            print("PASS: PCI device {} matches".format(address))
        else:
            print(
                "FAIL: PCI device {} differs from expectation".format(address)
            )
            failed = True
    return 1 if failed else 0


def main():
    """Return 0 for matches, 1 for mismatches, 2 for input/read errors."""
    try:
        source = os.environ.get("BLUEFIELD_EXPECTED_PCI", "")
        if not source:
            raise ValueError("Supply BLUEFIELD_EXPECTED_PCI expectations file")
        expected = read_expectations(source)
        print("PCI expectations: " + source)
        return check_devices(expected)
    except (OSError, UnicodeError, ValueError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
