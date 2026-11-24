#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Read-only DOCA device queries and representative runtime linkage."""

import json
import os
import re
import subprocess
import sys

from bluefield_pci import read_expectations

TOOL = "/opt/mellanox/doca/tools/doca_caps"


def query(args):
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=30,
        env=dict(os.environ, LC_ALL="C"),
    )
    print("Command: {}; exit: {}".format(" ".join(args), result.returncode))
    print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode:
        raise ValueError("DOCA evidence query failed")
    return result.stdout


def devices(output):
    data = json.loads(output)
    rows = data.get("devices") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("Require nonempty DOCA devices list")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(
            row.get("pci_addr"), str
        ):
            raise ValueError("Invalid DOCA device identity")
        address = row["pci_addr"]
        if address in result:
            raise ValueError("Duplicate DOCA device: " + address)
        result[address] = row
    return result


def check(expected):
    enumerated = devices(query([TOOL, "--list-devs", "--format", "json"]))
    for address in expected:
        if address not in enumerated:
            raise ValueError("Expected DOCA device missing: " + address)
        common = enumerated[address].get("common")
        if not isinstance(common, dict) or not common:
            raise ValueError("Missing DOCA enumeration details: " + address)
        detail = devices(
            query(
                [
                    TOOL,
                    "--pci-addr",
                    address,
                    "--lib",
                    "common",
                    "--format",
                    "json",
                ]
            )
        )
        if set(detail) != {address}:
            raise ValueError("Capability response identifies wrong device")
        capabilities = detail[address].get("libraries", {}).get("common")
        if (
            not isinstance(capabilities, dict)
            or not capabilities
            or any(
                not isinstance(k, str)
                or not k
                or v
                not in (
                    "supported",
                    "unsupported",
                )
                for k, v in capabilities.items()
            )
        ):
            raise ValueError("Invalid common capability response: " + address)
        print("Verified DOCA enumeration/common query: " + address)
    linkage = query(["ldd", TOOL])
    if "not found" in linkage or not linkage.strip():
        raise ValueError("Unresolved runtime dependencies")
    for library in ("libdoca_argp", "libdoca_common"):
        if not re.search(
            r"^\s*" + library + r"\.so[^\s]*\s+=>\s+/\S+", linkage, re.M
        ):
            raise ValueError("Required resolved linkage absent: " + library)
    print("PASS: DOCA device queries and representative linkage verified")
    print("No DMA/RDMA traffic, acceleration or optional capability assertion")


def main():
    try:
        source = os.environ.get("BLUEFIELD_EXPECTED_PCI", "")
        if not source:
            raise ValueError("Supply BLUEFIELD_EXPECTED_PCI expectations file")
        check(read_expectations(source))
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
