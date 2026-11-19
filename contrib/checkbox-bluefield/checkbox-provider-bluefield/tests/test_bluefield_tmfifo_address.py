# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Exercise tmfifo address matching with simulated discovery and ip output."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
SPEC = importlib.util.spec_from_file_location(
    "bluefield_tmfifo_address", BIN / "bluefield_tmfifo_address.py"
)
helper = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(BIN)] + sys.path):
    SPEC.loader.exec_module(helper)

INTERFACES = {
    "renamed_fifo": {"driver": "virtio_net", "parent_driver": "bf-tmfifo"},
    "other_virtio": {"driver": "virtio_net", "parent_driver": "other"},
}
OBSERVATION = [
    {
        "ifname": "renamed_fifo",
        "addr_info": [
            {"local": "192.168.100.2", "prefixlen": 30},
            {"local": "fe80::1234", "prefixlen": 64},
        ],
    }
]


class TmfifoAddressTests(unittest.TestCase):
    def run_check(
        self,
        value="192.168.100.2/30",
        interfaces=INTERFACES,
        observation=OBSERVATION,
        error=None,
    ):
        environment = (
            {}
            if value is None
            else {"BLUEFIELD_EXPECTED_TMFIFO_ADDRESS": value}
        )
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(
                helper, "discover_interfaces", return_value=interfaces
            ) as discover:
                with patch.object(helper.subprocess, "run") as query:
                    query.return_value.stdout = json.dumps(observation)
                    query.side_effect = error
                    with contextlib.redirect_stdout(output):
                        with contextlib.redirect_stderr(output):
                            status = helper.main()
        return status, output.getvalue(), discover, query

    def test_exact_address_passes_with_renamed_interface_and_extra_addresses(
        self,
    ):
        status, output, _, query = self.run_check()
        self.assertEqual(status, 0)
        self.assertIn("Observed tmfifo interface: renamed_fifo", output)
        self.assertIn("192.168.100.2/30, fe80::1234/64", output)
        self.assertEqual(
            query.call_args.args[0],
            ["ip", "-j", "address", "show", "dev", "renamed_fifo"],
        )
        self.assertEqual(query.call_args.kwargs["timeout"], 30)
        self.assertTrue(query.call_args.kwargs["check"])

    def test_wrong_address_or_prefix_fails(self):
        for value in ["192.168.100.1/30", "192.168.100.2/24"]:
            with self.subTest(value=value):
                status, output, _, _ = self.run_check(value=value)
                self.assertEqual(status, 1)
                self.assertIn("is absent", output)

    def test_unassigned_address_or_missing_interface_record_fails(self):
        for observation in [
            [],
            [{"ifname": "other", "addr_info": OBSERVATION[0]["addr_info"]}],
            [{"ifname": "renamed_fifo", "addr_info": []}],
            OBSERVATION + OBSERVATION,
        ]:
            with self.subTest(observation=observation):
                self.assertEqual(self.run_check(observation=observation)[0], 1)

    def test_missing_or_ambiguous_tmfifo_cannot_pass_or_query_ip(self):
        for interfaces in [
            {},
            {"other": INTERFACES["other_virtio"]},
            dict(INTERFACES, duplicate=INTERFACES["renamed_fifo"]),
        ]:
            with self.subTest(interfaces=interfaces):
                status, _, _, query = self.run_check(interfaces=interfaces)
                self.assertEqual(status, 1)
                query.assert_not_called()

    def test_invalid_or_missing_input_fails_before_discovery(self):
        for value in [
            None,
            "",
            "192.168.100.2",
            "invalid/30",
            "192.168.100.2/33",
            "192.168.100.2/30 ",
        ]:
            with self.subTest(value=value):
                status, _, discover, query = self.run_check(value=value)
                self.assertEqual(status, 2)
                discover.assert_not_called()
                query.assert_not_called()

    def test_ipv6_is_compared_as_an_address_not_text(self):
        status, _, _, _ = self.run_check(value="fe80:0:0:0:0:0:0:1234/64")
        self.assertEqual(status, 0)

    def test_invalid_query_output_fails(self):
        for observation in [
            {},
            [None],
            [{"ifname": "renamed_fifo"}],
            [{"ifname": "renamed_fifo", "addr_info": [None]}],
            [
                {
                    "ifname": "renamed_fifo",
                    "addr_info": [
                        {"local": "not-an-address", "prefixlen": 30}
                    ],
                }
            ],
        ]:
            with self.subTest(observation=observation):
                self.assertEqual(self.run_check(observation=observation)[0], 2)

    def test_query_errors_fail(self):
        for error in [
            FileNotFoundError("ip"),
            subprocess.CalledProcessError(1, "ip"),
            subprocess.TimeoutExpired("ip", 30),
        ]:
            with self.subTest(error=error):
                self.assertEqual(self.run_check(error=error)[0], 2)

    def test_discovery_errors_fail(self):
        with patch.dict(
            os.environ,
            {"BLUEFIELD_EXPECTED_TMFIFO_ADDRESS": "192.168.100.2/30"},
        ):
            with patch.object(
                helper,
                "discover_interfaces",
                side_effect=PermissionError("denied"),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(helper.main(), 2)


if __name__ == "__main__":
    unittest.main()
