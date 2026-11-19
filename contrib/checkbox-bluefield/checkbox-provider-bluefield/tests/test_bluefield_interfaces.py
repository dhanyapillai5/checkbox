# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Test role-based discovery independently of hardware and interface names."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = (
    Path(__file__).resolve().parents[1] / "bin" / "bluefield_interfaces.py"
)
SPEC = importlib.util.spec_from_file_location("bluefield_interfaces", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)

ROLES = [
    {"flavour": "physical", "port": 0},
    {"flavour": "pcipf", "controller": 1, "pfnum": 0, "external": True},
    {"flavour": "pcisf", "controller": 0, "pfnum": 0, "sfnum": 0},
]


class InterfaceExpectationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "expected.json"
        self.source.write_text(json.dumps(ROLES))
        self.net = self.root / "net"
        self.net.mkdir()
        self.ports = {}
        for index, role in enumerate(ROLES):
            name = "renamed_{}".format(index)
            (self.net / name).mkdir()
            self.ports[str(index)] = dict(role, type="eth", netdev=name)

    def check(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = helper.check_interfaces(
                ROLES, {"port": self.ports}, self.net
            )
        return status, output.getvalue()

    def test_roles_match_with_arbitrary_names_and_extra_ports(self):
        self.ports["extra"] = {"type": "eth", "flavour": "virtual"}
        self.assertEqual(helper.read_expectations(self.source), ROLES)
        status, output = self.check()
        self.assertEqual(status, 0)
        for index in range(3):
            self.assertIn(
                "interface renamed_{} is present".format(index), output
            )

    def test_missing_and_ambiguous_roles_fail(self):
        del self.ports["0"]
        self.ports["duplicate"] = copy.deepcopy(self.ports["1"])
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertIn("found 0", output)
        self.assertIn("found 2", output)
        self.assertIn("PASS:", output)

    def test_wrong_role_fields_or_types_cannot_match(self):
        for key, value in [
            ("controller", 2),
            ("pfnum", 1),
            ("external", False),
            ("external", 1),
            ("type", "ib"),
        ]:
            with self.subTest(key=key, value=value):
                with patch.dict(self.ports["1"], {key: value}):
                    self.assertEqual(self.check()[0], 1)
        self.ports["2"]["sfnum"] = 1
        self.assertEqual(self.check()[0], 1)

    def test_missing_netdev_or_absent_sysfs_interface_fails(self):
        for name in [None, "absent", ["invalid"]]:
            with self.subTest(name=name):
                self.ports["0"]["netdev"] = name
                self.assertEqual(self.check()[0], 1)

    def test_same_interface_cannot_satisfy_two_roles(self):
        self.ports["1"]["netdev"] = self.ports["0"]["netdev"]
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertIn("more than one", output)

    def test_invalid_expectations_cannot_pass(self):
        for expected in [
            [],
            {},
            ["invalid"],
            ROLES + ROLES,
            [{"flavour": "physical"}],
            [{"flavour": []}],
            [{"flavour": "physical", "port": True}],
            [{"flavour": "physical", "port": -1}],
            [{"flavour": "physical", "port": 0, "netdev": "p0"}],
        ]:
            with self.subTest(expected=expected):
                self.source.write_text(json.dumps(expected))
                with self.assertRaises(ValueError):
                    helper.read_expectations(self.source)

    def test_malformed_observation_and_unreadable_sysfs_cannot_pass(self):
        for observation in [[], {}, {"port": []}, {"port": {"bad": None}}]:
            with self.subTest(observation=observation):
                with self.assertRaises(ValueError):
                    helper.check_interfaces(ROLES, observation, self.net)
        with self.assertRaises(OSError):
            helper.check_interfaces(ROLES, {"port": {}}, self.net / "absent")

    def test_main_reports_query_and_input_errors(self):
        with patch.dict(os.environ, {"BLUEFIELD_EXPECTED_INTERFACES": ""}):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(helper.main(), 2)
        for error in [
            FileNotFoundError("devlink"),
            subprocess.CalledProcessError(1, "devlink"),
            subprocess.TimeoutExpired("devlink", 30),
        ]:
            with self.subTest(error=error):
                with patch.dict(
                    os.environ,
                    {"BLUEFIELD_EXPECTED_INTERFACES": str(self.source)},
                ):
                    with patch.object(
                        helper.subprocess, "run", side_effect=error
                    ):
                        with contextlib.redirect_stderr(io.StringIO()):
                            self.assertEqual(helper.main(), 2)


if __name__ == "__main__":
    unittest.main()
