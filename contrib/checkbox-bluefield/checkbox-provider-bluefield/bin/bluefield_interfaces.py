#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Find required DPU interfaces by devlink identity and report their names."""

import json
import os
from pathlib import Path
import subprocess
import sys


def read_expectations(path):
    """Require complete role selectors without interface-name assumptions."""
    expected = json.loads(Path(path).read_text())
    if not isinstance(expected, list) or not expected:
        raise ValueError("Expected a nonempty JSON list of devlink identities")
    fields = {
        "physical": {"port"},
        "pcipf": {"controller", "pfnum", "external"},
        "pcisf": {"controller", "pfnum", "sfnum"},
    }
    seen = []
    for role in expected:
        if not isinstance(role, dict):
            raise ValueError("Each expected identity must be an object")
        flavour = role.get("flavour")
        if not isinstance(flavour, str) or flavour not in fields:
            raise ValueError("Expected physical, pcipf or pcisf flavour")
        if set(role) != fields[flavour] | {"flavour"}:
            raise ValueError(
                "Incomplete or unknown identity fields: " + str(role)
            )
        for key in fields[flavour]:
            value = role[key]
            if key == "external":
                valid = type(value) is bool
            else:
                valid = type(value) is int and value >= 0
            if not valid:
                raise ValueError("Invalid identity field: " + key)
        if role in seen:
            raise ValueError("Duplicate expected identity")
        seen.append(role)
    return expected


def check_interfaces(expected, observation, root=Path("/sys/class/net")):
    """Require one Ethernet netdev per identity, allowing additional ports."""
    if not isinstance(observation, dict) or not isinstance(
        observation.get("port"), dict
    ):
        raise ValueError("Invalid devlink JSON: expected port mapping")
    ports = observation["port"]
    if any(not isinstance(port, dict) for port in ports.values()):
        raise ValueError("Invalid devlink port entry")
    interfaces = {path.name for path in root.iterdir()}
    failed = False
    used = set()
    for role in expected:
        print("Expected identity: " + json.dumps(role, sort_keys=True))
        matches = [
            (key, port)
            for key, port in ports.items()
            if port.get("type") == "eth"
            and all(
                type(port.get(field)) is type(value) and port[field] == value
                for field, value in role.items()
            )
        ]
        if len(matches) != 1:
            print(
                "FAIL: expected one matching port; found {}".format(
                    len(matches)
                )
            )
            failed = True
            continue
        key, port = matches[0]
        name = port.get("netdev")
        print("Observed devlink port: {}; interface: {}".format(key, name))
        if not isinstance(name, str) or name not in interfaces:
            print("FAIL: matching port has no existing network interface")
            failed = True
        elif name in used:
            print("FAIL: interface matched more than one required identity")
            failed = True
        else:
            print("PASS: required interface {} is present".format(name))
            used.add(name)
    return 1 if failed else 0


def main():
    """Return 0 for matches, 1 for missing/ambiguous roles, 2 for errors."""
    try:
        source = os.environ.get("BLUEFIELD_EXPECTED_INTERFACES", "")
        if not source:
            raise ValueError("Supply BLUEFIELD_EXPECTED_INTERFACES JSON file")
        expected = read_expectations(source)
        result = subprocess.run(
            ["devlink", "-j", "port", "show"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            env=dict(os.environ, LC_ALL="C"),
        )
        print("Interface expectations: " + source)
        return check_interfaces(expected, json.loads(result.stdout))
    except (
        OSError,
        UnicodeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
