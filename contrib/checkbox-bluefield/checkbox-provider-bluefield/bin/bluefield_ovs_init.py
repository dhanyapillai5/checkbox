#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Exercise temporary OVS bridge/port initialization, with verified cleanup."""

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import uuid


def query(*args):
    result = subprocess.run(
        ["ovs-vsctl", "--timeout=20", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=dict(os.environ, LC_ALL="C"),
    )
    print("Command: ovs-vsctl " + " ".join(args))
    print("Exit: {}; stdout: {}".format(result.returncode, result.stdout))
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode:
        raise ValueError("OVS command failed")
    return result.stdout


def decode(value):
    if isinstance(value, list) and len(value) == 2:
        kind, data = value
        if kind == "map":
            return dict(data)
        if kind == "set":
            return data
        if kind == "uuid":
            return data
    return value


def rows(table, columns):
    data = json.loads(
        query("--format=json", "--columns=" + columns, "list", table)
    )
    if (
        not isinstance(data, dict)
        or data.get("headings") != columns.split(",")
        or not isinstance(data.get("data"), list)
    ):
        raise ValueError("Invalid OVS table response: " + table)
    result = {}
    for row in data["data"]:
        if not isinstance(row, list) or len(row) != len(data["headings"]):
            raise ValueError("Invalid OVS row: " + table)
        item = dict(zip(data["headings"], map(decode, row)))
        identity = item.get("name", item.get("_uuid"))
        if not isinstance(identity, str) or identity in result:
            raise ValueError("Invalid or duplicate OVS identity")
        result[identity] = item
    return result


def snapshot():
    # Configuration only: omit counters and changing runtime state.
    return {
        "Open_vSwitch": rows("Open_vSwitch", "_uuid,other_config"),
        "Bridge": rows(
            "Bridge",
            "_uuid,name,datapath_type,ports,other_config,external_ids",
        ),
        "Port": rows(
            "Port", "_uuid,name,interfaces,bond_mode,tag,trunks,external_ids"
        ),
        "Interface": rows("Interface", "_uuid,name,type,options,external_ids"),
    }


def read_expectations(text):
    policy = json.loads(text)
    if (
        not isinstance(policy, dict)
        or set(policy) != {"other_config", "datapath_type"}
        or not isinstance(policy["other_config"], dict)
        or not policy["other_config"]
        or not isinstance(policy["datapath_type"], str)
        or not re.fullmatch(r"[a-z][a-z0-9_-]*", policy["datapath_type"])
    ):
        raise ValueError("Require other_config map and explicit datapath_type")
    for key, value in policy["other_config"].items():
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]*", key)
            or not isinstance(value, str)
            or not re.fullmatch(r"[a-zA-Z0-9_.-]+", value)
        ):
            raise ValueError("Invalid other_config expectation")
    return policy


def canonical(state):
    # OVSDB sets and maps have no meaningful ordering.
    if isinstance(state, dict):
        return {key: canonical(value) for key, value in state.items()}
    if isinstance(state, list):
        return sorted((canonical(v) for v in state), key=repr)
    return state


def cleanup(before, bridge, port, owner):
    bridges = rows("Bridge", "_uuid,name,ports,external_ids")
    if bridge in bridges:
        record = bridges[bridge]
        if record["external_ids"].get("checkbox-owner") != owner:
            raise ValueError("Cleanup refused: bridge ownership changed")
        ports = rows("Port", "_uuid,name")
        allowed = {
            ports[name]["_uuid"] for name in (bridge, port) if name in ports
        }
        attached = record["ports"]
        attached = attached if isinstance(attached, list) else [attached]
        attached = {decode(value) for value in attached}
        if not attached <= allowed:
            raise ValueError(
                "Cleanup refused: unexpected ports on test bridge"
            )
        query("--if-exists", "del-br", bridge)
    after = snapshot()
    if canonical(before) != canonical(after):
        raise ValueError(
            "Cleanup/preservation check failed: OVS state differs"
        )
    if any(
        (Path("/sys/class/net") / name).exists() for name in (bridge, port)
    ):
        raise ValueError("Cleanup failed: temporary netdev still exists")
    print("PASS: temporary objects removed; pre-existing OVS config preserved")


def check(policy):
    print("Expected OVS initialization policy: " + json.dumps(policy))
    before = snapshot()
    globals_ = list(before["Open_vSwitch"].values())
    if len(globals_) != 1 or not isinstance(globals_[0]["other_config"], dict):
        raise ValueError("Require one Open_vSwitch configuration row")
    actual = globals_[0]["other_config"]
    mismatches = [
        key
        for key, value in policy["other_config"].items()
        if actual.get(key) != value
    ]
    if mismatches:
        raise ValueError("OVS other_config mismatch: " + ", ".join(mismatches))
    owner = uuid.uuid4().hex
    bridge, port = "bfc" + owner[:10], "bfp" + owner[:10]
    if any(
        name in before[table]
        for table in ("Bridge", "Port", "Interface")
        for name in (bridge, port)
    ):
        raise ValueError("Temporary name collision; no changes made")
    if any(
        (Path("/sys/class/net") / name).exists() for name in (bridge, port)
    ):
        raise ValueError("Temporary netdev name collision; no changes made")
    # All creates and ownership markers are atomic. A timeout may still commit;
    # always attempt ownership-checked cleanup after issuing this transaction.
    try:
        query(
            "add-br",
            bridge,
            "--",
            "set",
            "Bridge",
            bridge,
            "datapath_type=" + policy["datapath_type"],
            "external_ids:checkbox-owner=" + owner,
            "--",
            "add-port",
            bridge,
            port,
            "--",
            "set",
            "Interface",
            port,
            "type=internal",
        )
        bridges = rows("Bridge", "name,datapath_type,datapath_id")
        observed = bridges.get(bridge, {})
        if (
            observed.get("datapath_type") != policy["datapath_type"]
            or not isinstance(observed.get("datapath_id"), str)
            or not re.fullmatch(r"[0-9a-fA-F]{16}", observed["datapath_id"])
        ):
            raise ValueError("Temporary bridge datapath did not initialize")
        interfaces = rows("Interface", "name,type,ofport,error")
        for name in (bridge, port):
            interface = interfaces.get(name, {})
            if (
                interface.get("type") != "internal"
                or type(interface.get("ofport")) is not int
                or interface["ofport"] <= 0
                or interface.get("error") not in ([], "")
            ):
                raise ValueError("Interface initialization failed: " + name)
        print("PASS: temporary bridge datapath and internal port initialized")
    except BaseException as exc:
        print("FAIL: initialization: {}".format(exc), file=sys.stderr)
        raise
    finally:
        cleanup(before, bridge, port, owner)


def main():
    def interrupted(signum, frame):
        raise InterruptedError(
            "OVS check interrupted by signal {}".format(signum)
        )

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        source = os.environ.get("BLUEFIELD_OVS_INIT_POLICY", "")
        if not source or not Path(source).is_absolute():
            raise ValueError("Supply absolute BLUEFIELD_OVS_INIT_POLICY")
        check(read_expectations(Path(source).read_text()))
        return 0
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
