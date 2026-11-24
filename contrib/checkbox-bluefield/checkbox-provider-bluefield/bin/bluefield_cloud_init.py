#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Assert cloud-init completion with narrowly guarded reporting warnings."""

import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit

from bluefield_network_config import verify_deployment_network
import yaml

RENAME_WARNING = re.compile(
    r"Failed to rename devices: Failed to apply network config names: "
    r"\[nic not present\] Cannot rename mac=([0-9a-f]{2}(?::[0-9a-f]{2}){5}) "
    r"to ([A-Za-z0-9_.-]{1,15}), not available\."
)


def recovered_rename(message):
    """Require the warned identity in verified MAAS network configuration."""
    match = RENAME_WARNING.fullmatch(message)
    if not match:
        return False
    return match.groups() in verify_deployment_network()


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
    """Require enforced deployment addressing and a default route."""
    from bluefield_network_config import load_config

    profiles = load_config()
    if not any(
        p["addresses"]
        and any(
            r["to"] in ("default", "0.0.0.0/0", "::/0") for r in p["routes"]
        )
        for p in profiles
    ):
        raise ValueError("MAAS reporting guard requires address/default route")
    return bool(verify_deployment_network())


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
    rename_warnings = set()
    issues = set()
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
                elif category == "WARNING" and RENAME_WARNING.fullmatch(
                    message
                ):
                    rename_warnings.add(message)
                else:
                    issues.add(message)
                    failed = True
    for message in sorted(issues):
        print("FAIL: unclassified cloud-init issue: " + message)
    if not failed and datasource == expected:
        for message in sorted(rename_warnings):
            if recovered_rename(message):
                print("WARNING: recovered early rename issue: " + message)
            else:
                print("FAIL: rename recovery not verified: " + message)
                failed = True
    if (status_code == 2 or extended == "degraded done") and not (
        warnings or rename_warnings
    ):
        failed = True
    if warnings:
        for warning in sorted(warnings):
            print("WARNING: " + warning)
        if not failed and datasource == expected == "maas":
            if not management_ready():
                print("FAIL: deployment address/default route not verified")
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
                "; reviewed warnings retained with verified postconditions"
                if warnings or rename_warnings
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
        KeyError,
        yaml.YAMLError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
