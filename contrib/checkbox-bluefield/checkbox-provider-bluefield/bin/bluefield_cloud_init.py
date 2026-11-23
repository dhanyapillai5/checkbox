#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert cloud-init completion with narrowly guarded reporting warnings."""

import json
import ipaddress
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit

from bluefield_management import discover_interfaces


def reporting_warning(message, details):
    """Recognise only pre-network MAAS event delivery failures."""
    if details.get("datasource") != "maas" or not message.startswith(
        "Failed posting event: "
    ):
        return False
    try:
        endpoint = urlsplit(details["detail"].split("[", 1)[1].rstrip("]"))
        payload = message[len("Failed posting event: ") :]
        event, end = json.JSONDecoder().raw_decode(payload)
        tail = payload[end:]
        return (
            endpoint.scheme == "http"
            and bool(endpoint.hostname)
            and event.get("name")
            in ("init-local/check-cache", "init-local/search-MAASLocal")
            and event.get("origin") == "cloudinit"
            and event.get("event_type") in ("start", "finish")
            and tail.startswith(". This was caused by: HTTPConnectionPool(")
            and "host='{}', port={}".format(
                endpoint.hostname, endpoint.port or 80
            )
            in tail
            and "/MAAS/metadata/status/" in tail
            and (
                "Failed to establish a new connection: "
                "[Errno 101] Network is unreachable"
            )
            in tail
        )
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        return False


def management_ready():
    """Verify independent address/prefix and default gateway on the OOB NIC."""
    value = os.environ.get("BLUEFIELD_EXPECTED_OOB_ADDRESS", "")
    if "/" not in value:
        raise ValueError(
            "Supply BLUEFIELD_EXPECTED_OOB_ADDRESS address/prefix"
        )
    address = ipaddress.ip_interface(value)
    gateway = ipaddress.ip_address(
        os.environ.get("BLUEFIELD_EXPECTED_OOB_GATEWAY", "")
    )
    if address.version != gateway.version:
        raise ValueError("OOB address and gateway families differ")
    matches = [
        name
        for name, identity in discover_interfaces().items()
        if identity["driver"] == "mlxbf_gige"
    ]
    if len(matches) != 1:
        return False
    name = matches[0]
    addresses = run_command(["ip", "-j", "address", "show", "dev", name], 30)
    routes = run_command(
        [
            "ip",
            "-j",
            "-{}".format(address.version),
            "route",
            "show",
            "default",
        ],
        30,
    )
    if addresses.returncode or routes.returncode:
        raise ValueError("Unable to query management address/default route")
    assigned = any(
        item.get("ifname") == name
        and any(
            entry.get("local") == str(address.ip)
            and entry.get("prefixlen") == address.network.prefixlen
            and not entry.get("tentative", False)
            and not entry.get("dadfailed", False)
            for entry in item.get("addr_info", [])
        )
        for item in json.loads(addresses.stdout)
    )
    routed = any(
        item.get("dst") == "default"
        and item.get("dev") == name
        and item.get("gateway") == str(gateway)
        and item.get("type", "unicast") == "unicast"
        for item in json.loads(routes.stdout)
    )
    print("Expected OOB on {}: {}; gateway {}".format(name, address, gateway))
    return assigned and routed


def check_status(details, status_code, datasource, expected):
    """Accept only reviewed reporting warnings with network proof."""
    if (
        not isinstance(details, dict)
        or not isinstance(details.get("status"), str)
        or not isinstance(details.get("errors"), list)
    ):
        raise ValueError("Invalid cloud-init status JSON")
    print("Expected datasource: " + expected)
    print("Observed datasource: " + datasource)
    print("Cloud-init status details: " + json.dumps(details, sort_keys=True))
    failed = status_code not in (0, 2) or details["status"] != "done"
    extended = details.get("extended_status")
    if extended is not None and extended not in ("done", "degraded done"):
        failed = True
    warnings = set()
    for section in (
        details,
        *(v for v in details.values() if isinstance(v, dict)),
    ):
        if not isinstance(section.get("errors", []), list):
            raise ValueError("Invalid stage errors")
        if section.get("errors"):
            failed = True
        recoverable = section.get("recoverable_errors", {})
        if not isinstance(recoverable, dict):
            raise ValueError("Invalid recoverable errors")
        for category, messages in recoverable.items():
            if not isinstance(messages, list) or any(
                not isinstance(message, str) for message in messages
            ):
                raise ValueError("Invalid recoverable error messages")
            for message in messages:
                if category == "WARNING" and reporting_warning(
                    message, details
                ):
                    warnings.add(message)
                else:
                    print("FAIL: unclassified cloud-init issue: " + message)
                    failed = True
    if (status_code == 2 or extended == "degraded done") and not warnings:
        failed = True
    if warnings:
        for warning in sorted(warnings):
            print("WARNING: " + warning)
        if not failed and datasource == expected == "maas":
            if not management_ready():
                print("FAIL: required OOB address/default route not verified")
                failed = True
    if failed:
        print("FAIL: cloud-init has not completed cleanly")
    if datasource != expected:
        print("FAIL: cloud-init datasource differs from expectation")
        failed = True
    if not failed:
        print(
            "PASS: cloud-init completed with expected datasource"
            + (
                "; reporting warnings retained, OOB address/route verified"
                if warnings
                else "; no recorded errors"
            )
        )
    return 1 if failed else 0


def run_command(command, timeout):
    """Bound execution and preserve stdout/stderr even on command failures."""
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=dict(os.environ, LC_ALL="C"),
    )
    print("Command: {}; exit: {}".format(" ".join(command), result.returncode))
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result


def main():
    """Return 0 for healthy completion, 1 for failures, 2 for setup errors."""
    try:
        expected = os.environ.get("BLUEFIELD_EXPECTED_DATASOURCE", "")
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", expected):
            raise ValueError(
                "Supply BLUEFIELD_EXPECTED_DATASOURCE cloud-id value"
            )
        wait = run_command(["cloud-init", "status", "--wait"], 120)
        status = run_command(
            ["cloud-init", "status", "--long", "--format=json"], 30
        )
        datasource = run_command(["cloud-id"], 30)
        if datasource.returncode != 0 or status.returncode not in (0, 1, 2):
            raise ValueError(
                "Unable to obtain cloud-init status or datasource"
            )
        outcome = check_status(
            json.loads(status.stdout),
            status.returncode,
            datasource.stdout.strip(),
            expected,
        )
        if wait.returncode not in (0, 2) or (
            wait.returncode == 2 and status.returncode != 2
        ):
            print("FAIL: cloud-init wait did not complete successfully")
            return 1
        return outcome
    except subprocess.TimeoutExpired as exc:
        print(
            "FAIL: cloud-init command timed out: {}".format(exc),
            file=sys.stderr,
        )
        if exc.stdout:
            print(exc.stdout, file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return 1
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
