# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for temporary OVS initialization and cleanup."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin/bluefield_ovs_init.py"
SPEC = importlib.util.spec_from_file_location("ovs_init", SCRIPT)
ovs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ovs)

POLICY = {
    "other_config": {"doca-init": "true", "hw-offload": "true"},
    "datapath_type": "netdev",
}
BEFORE = {
    "Open_vSwitch": {
        "global": {
            "_uuid": "global",
            "other_config": {"doca-init": "true", "hw-offload": "true"},
        }
    },
    "Bridge": {"deployment": {"name": "deployment", "_uuid": "existing"}},
    "Port": {},
    "Interface": {},
}
OWNER = "a" * 32
BRIDGE, PORT = "bfc" + OWNER[:10], "bfp" + OWNER[:10]


class OvsInitializationTests(unittest.TestCase):
    def exercise(
        self,
        failure=None,
        datapath="0123456789abcdef",
        ofport=1,
        interface_error=None,
    ):
        bridge = {
            BRIDGE: {
                "name": BRIDGE,
                "datapath_type": "netdev",
                "datapath_id": datapath,
            }
        }
        interface = {
            name: {
                "name": name,
                "type": "internal",
                "ofport": ofport,
                "error": [] if interface_error is None else interface_error,
            }
            for name in (BRIDGE, PORT)
        }
        output = io.StringIO()
        with patch.object(
            ovs, "snapshot", return_value=copy.deepcopy(BEFORE)
        ), patch.object(ovs.uuid, "uuid4") as uuid, patch.object(
            ovs.Path, "exists", return_value=False
        ), patch.object(
            ovs, "query", side_effect=failure
        ) as query, patch.object(
            ovs, "rows", side_effect=[bridge, interface]
        ), patch.object(
            ovs, "cleanup"
        ) as cleanup, contextlib.redirect_stdout(
            output
        ), contextlib.redirect_stderr(
            output
        ):
            uuid.return_value.hex = OWNER
            error = None
            try:
                ovs.check(POLICY)
            except BaseException as exc:
                error = exc
        return error, query, cleanup, output.getvalue()

    def test_create_explicit_datapath_internal_port_and_cleanup(self):
        error, query, cleanup, output = self.exercise()
        self.assertIsNone(error)
        args = query.call_args.args
        self.assertEqual(args[:2], ("add-br", BRIDGE))
        self.assertIn("datapath_type=netdev", args)
        self.assertIn("type=internal", args)
        self.assertIn("external_ids:checkbox-owner=" + OWNER, args)
        self.assertNotIn("Open_vSwitch", args)
        cleanup.assert_called_once_with(BEFORE, BRIDGE, PORT, OWNER)
        self.assertIn("PASS: temporary bridge", output)

    def test_failed_or_timed_out_create_and_interrupt_still_clean_up(self):
        for failure in (
            ValueError("create failed"),
            subprocess.TimeoutExpired("ovs-vsctl", 30),
            KeyboardInterrupt(),
            InterruptedError("terminated"),
        ):
            with self.subTest(failure=failure):
                error, _, cleanup, _ = self.exercise(failure=failure)
                self.assertIs(error, failure)
                cleanup.assert_called_once()

    def test_missing_datapath_or_failed_interface_cannot_pass(self):
        for kwargs in (
            {"datapath": []},
            {"ofport": -1},
            {"ofport": []},
            {"interface_error": "could not open device"},
        ):
            with self.subTest(kwargs=kwargs):
                error, _, cleanup, _ = self.exercise(**kwargs)
                self.assertIsInstance(error, ValueError)
                cleanup.assert_called_once()

    def test_global_mismatch_fails_without_mutating(self):
        before = copy.deepcopy(BEFORE)
        before["Open_vSwitch"]["global"]["other_config"].pop("hw-offload")
        with patch.object(ovs, "snapshot", return_value=before), patch.object(
            ovs, "query"
        ) as query, contextlib.redirect_stdout(
            io.StringIO()
        ), self.assertRaises(
            ValueError
        ):
            ovs.check(POLICY)
        query.assert_not_called()

    def test_collision_prevents_mutation(self):
        before = copy.deepcopy(BEFORE)
        before["Bridge"][BRIDGE] = {}
        with patch.object(ovs, "snapshot", return_value=before), patch.object(
            ovs.uuid, "uuid4"
        ) as uuid, patch.object(
            ovs, "query"
        ) as query, contextlib.redirect_stdout(
            io.StringIO()
        ):
            uuid.return_value.hex = OWNER
            with self.assertRaises(ValueError):
                ovs.check(POLICY)
        query.assert_not_called()

    def test_cleanup_deletes_owned_bridge_and_checks_snapshot(self):
        bridges = {
            BRIDGE: {
                "ports": [["uuid", "local"], ["uuid", "port"]],
                "external_ids": {"checkbox-owner": OWNER},
            }
        }
        ports = {BRIDGE: {"_uuid": "local"}, PORT: {"_uuid": "port"}}
        with patch.object(
            ovs, "rows", side_effect=[bridges, ports]
        ), patch.object(ovs, "query") as query, patch.object(
            ovs, "snapshot", return_value=copy.deepcopy(BEFORE)
        ), contextlib.redirect_stdout(
            io.StringIO()
        ):
            ovs.cleanup(BEFORE, BRIDGE, PORT, OWNER)
        query.assert_called_once_with("--if-exists", "del-br", BRIDGE)

    def test_cleanup_refuses_changed_owner_or_unexpected_ports(self):
        for owner, attached in (("other", []), (OWNER, [["uuid", "foreign"]])):
            bridges = {
                BRIDGE: {
                    "ports": attached,
                    "external_ids": {"checkbox-owner": owner},
                }
            }
            with patch.object(
                ovs, "rows", side_effect=[bridges, {}]
            ), patch.object(ovs, "query") as query, self.assertRaises(
                ValueError
            ):
                ovs.cleanup(BEFORE, BRIDGE, PORT, OWNER)
            query.assert_not_called()

    def test_cleanup_missing_bridge_still_detects_orphans_or_existing_drift(
        self,
    ):
        after = copy.deepcopy(BEFORE)
        after["Interface"][PORT] = {"name": PORT}
        with patch.object(ovs, "rows", return_value={}), patch.object(
            ovs, "snapshot", return_value=after
        ), self.assertRaises(ValueError):
            ovs.cleanup(BEFORE, BRIDGE, PORT, OWNER)

    def test_cleanup_failure_cannot_be_a_pass(self):
        with patch.object(ovs, "cleanup", side_effect=ValueError("cleanup")):
            # exercise installs its own cleanup mock; test the caller directly.
            with patch.object(
                ovs, "snapshot", return_value=BEFORE
            ), patch.object(ovs.uuid, "uuid4") as uuid, patch.object(
                ovs.Path, "exists", return_value=False
            ), patch.object(
                ovs, "query", side_effect=ValueError("create")
            ), contextlib.redirect_stdout(
                io.StringIO()
            ), contextlib.redirect_stderr(
                io.StringIO()
            ):
                uuid.return_value.hex = OWNER
                with self.assertRaisesRegex(ValueError, "cleanup"):
                    ovs.check(POLICY)

    def test_ovs_json_decode_and_malformed_output(self):
        data = {
            "headings": ["name", "external_ids", "ports"],
            "data": [
                [
                    "br",
                    ["map", [["owner", "example"]]],
                    ["set", [["uuid", "id"]]],
                ]
            ],
        }
        with patch.object(ovs, "query", return_value=json.dumps(data)):
            rows = ovs.rows("Bridge", "name,external_ids,ports")
        self.assertEqual(rows["br"]["external_ids"], {"owner": "example"})
        for value in ("invalid", "{}", json.dumps({**data, "data": [["br"]]})):
            with self.subTest(value=value), patch.object(
                ovs, "query", return_value=value
            ), self.assertRaises(ValueError):
                ovs.rows("Bridge", "name,external_ids,ports")

    def test_invalid_or_empty_policy_fails(self):
        for policy in (
            {},
            {**POLICY, "datapath_type": "bad type"},
            {**POLICY, "other_config": {}},
            {**POLICY, "other_config": {"doca-init": True}},
        ):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                ovs.read_expectations(json.dumps(policy))


if __name__ == "__main__":
    unittest.main()
