#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Temporarily assign a DPU tmfifo IPv4 address and verify restoration."""

import ipaddress
import json
import os
import signal
import subprocess
import sys

from bluefield_management import discover_interfaces


def command(*args):
    result = subprocess.run(
        ["ip", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=dict(os.environ, LC_ALL="C"),
    )
    print("Command: ip {}; exit: {}".format(" ".join(args), result.returncode))
    print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode:
        raise ValueError("ip command failed")
    return result.stdout


def observe(name):
    data = json.loads(command("-j", "address", "show", "dev", name))
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError("Require one tmfifo address record")
    row = data[0]
    if (
        not isinstance(row, dict)
        or row.get("ifname") != name
        or type(row.get("ifindex")) is not int
        or not isinstance(row.get("flags"), list)
        or not isinstance(row.get("addr_info"), list)
    ):
        raise ValueError("Invalid tmfifo address record")
    addresses = set()
    for entry in row["addr_info"]:
        if (
            not isinstance(entry, dict)
            or type(entry.get("prefixlen")) is not int
        ):
            raise ValueError("Invalid tmfifo address")
        addresses.add(
            str(
                ipaddress.ip_interface(
                    "{}/{}".format(entry.get("local"), entry["prefixlen"])
                )
            )
        )
    return row["ifindex"], "UP" in row["flags"], addresses


def check(expected):
    matches = [
        name
        for name, identity in discover_interfaces().items()
        if identity == {"driver": "virtio_net", "parent_driver": "bf-tmfifo"}
    ]
    if len(matches) != 1:
        raise ValueError("Require exactly one driver-discovered tmfifo")
    name = matches[0]
    before = observe(name)
    print(
        "Original tmfifo {}: {!r}; test address: {}".format(
            name, before, expected
        )
    )
    if not before[1] and before[2]:
        raise ValueError(
            "DOWN tmfifo has existing addresses; refusing state changes"
        )
    if any(
        ipaddress.ip_interface(a).ip == expected.ip and a != str(expected)
        for a in before[2]
    ):
        raise ValueError("Test IP already exists with another prefix")
    added = str(expected) not in before[2]
    try:
        if added:
            command(
                "address", "add", str(expected), "dev", name, "noprefixroute"
            )
        if not before[1]:
            command("link", "set", "dev", name, "up")
        current = observe(name)
        if (
            current[0] != before[0]
            or not current[1]
            or str(expected) not in current[2]
        ):
            raise ValueError("Temporary tmfifo address/UP verification failed")
        print("PASS: tmfifo UP with test address " + str(expected))
    finally:
        # A timed-out ip command may have taken effect. Observe before undoing.
        current = observe(name)
        if current[0] != before[0]:
            raise ValueError("Cleanup refused: tmfifo identity changed")
        failures = []
        if added and str(expected) in current[2]:
            try:
                command("address", "del", str(expected), "dev", name)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                failures.append(str(exc))
        if not before[1]:
            try:
                command("link", "set", "dev", name, "down")
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                failures.append(str(exc))
        if observe(name) != before:
            failures.append("original link state/addresses not restored")
        if failures:
            raise ValueError("tmfifo cleanup failed: " + "; ".join(failures))
        print("PASS: original tmfifo link state and addresses restored")


def main():
    def interrupted(signum, frame):
        raise InterruptedError("tmfifo trial interrupted")

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        value = os.environ.get("BLUEFIELD_TEST_TMFIFO_ADDRESS", "")
        if "/" not in value or any(char.isspace() for char in value):
            raise ValueError(
                "Supply BLUEFIELD_TEST_TMFIFO_ADDRESS as IPv4/prefix"
            )
        expected = ipaddress.IPv4Interface(value)
        if (
            expected.ip.is_unspecified
            or expected.ip.is_multicast
            or expected.ip.is_loopback
        ):
            raise ValueError("Require a unicast tmfifo test address")
        check(expected)
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
