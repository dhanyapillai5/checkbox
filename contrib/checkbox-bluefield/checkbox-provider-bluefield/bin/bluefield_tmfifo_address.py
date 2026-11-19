#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert a configured address/prefix on the driver-discovered DPU tmfifo."""

import ipaddress
import json
import os
import subprocess
import sys

from bluefield_management import discover_interfaces


def check_address(name, expected, observation):
    """Compare exact local address/prefix, allowing extra addresses."""
    if not isinstance(observation, list) or any(
        not isinstance(entry, dict) for entry in observation
    ):
        raise ValueError("Invalid ip JSON: expected interface objects")
    matches = [entry for entry in observation if entry.get("ifname") == name]
    if len(matches) != 1:
        print(
            "FAIL: expected one address record for {}; found {}".format(
                name, len(matches)
            )
        )
        return 1
    addresses = matches[0].get("addr_info")
    if not isinstance(addresses, list):
        raise ValueError("Invalid ip JSON: expected addr_info list")
    actual = []
    for address in addresses:
        if not isinstance(address, dict):
            raise ValueError("Invalid ip address entry")
        local, prefix = address.get("local"), address.get("prefixlen")
        if not isinstance(local, str) or type(prefix) is not int:
            raise ValueError("Invalid local address or prefix")
        actual.append(ipaddress.ip_interface("{}/{}".format(local, prefix)))
    print("Observed tmfifo interface: {}".format(name))
    print(
        "Observed addresses: {}".format(
            ", ".join(str(address) for address in actual) or "none"
        )
    )
    if expected not in actual:
        print("FAIL: expected tmfifo address {} is absent".format(expected))
        return 1
    print("PASS: tmfifo address {} is assigned".format(expected))
    return 0


def main():
    """Return 0 for an assigned address, 1 for mismatch, 2 for input/errors."""
    try:
        value = os.environ.get("BLUEFIELD_EXPECTED_TMFIFO_ADDRESS", "")
        if "/" not in value or any(char.isspace() for char in value):
            raise ValueError(
                "BLUEFIELD_EXPECTED_TMFIFO_ADDRESS must be an address/prefix"
            )
        expected = ipaddress.ip_interface(value)
        print("Expected tmfifo address: {}".format(expected))
        interfaces = discover_interfaces()
        matches = [
            name
            for name, identity in interfaces.items()
            if identity
            == {"driver": "virtio_net", "parent_driver": "bf-tmfifo"}
        ]
        if len(matches) != 1:
            print(
                "FAIL: expected one tmfifo interface; found {} ({})".format(
                    len(matches), ", ".join(matches)
                )
            )
            return 1
        name = matches[0]
        result = subprocess.run(
            ["ip", "-j", "address", "show", "dev", name],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            env=dict(os.environ, LC_ALL="C"),
        )
        return check_address(name, expected, json.loads(result.stdout))
    except (
        OSError,
        UnicodeError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
