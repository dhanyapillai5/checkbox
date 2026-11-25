# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Exercise temporary tmfifo address changes and restoration failures."""

import contextlib
import importlib.util
import io
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
SPEC = importlib.util.spec_from_file_location(
    "trial", BIN / "bluefield_tmfifo_trial.py"
)
trial = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(BIN)] + sys.path):
    SPEC.loader.exec_module(trial)

ADDRESS = "192.168.100.2/30"
IDENTITY = {"fifo": {"driver": "virtio_net", "parent_driver": "bf-tmfifo"}}


class TmfifoTrialTests(unittest.TestCase):
    def test_missing_invalid_or_nonunicast_input_prevents_discovery(self):
        for value in (
            "",
            "192.168.100.2",
            "bad/30",
            "::1/128",
            "127.0.0.1/8",
            "224.0.0.1/24",
            "0.0.0.0/30",
        ):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {"BLUEFIELD_TEST_TMFIFO_ADDRESS": value},
                clear=True,
            ), patch.object(
                trial, "discover_interfaces"
            ) as discover, contextlib.redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(trial.main(), 1)
                discover.assert_not_called()

    def test_observation_checks_identity_flags_and_addresses(self):
        good = [
            {
                "ifname": "fifo",
                "ifindex": 3,
                "flags": ["UP"],
                "addr_info": [{"local": "192.168.100.2", "prefixlen": 30}],
            }
        ]
        with patch.object(trial, "command", return_value=json.dumps(good)):
            self.assertEqual(trial.observe("fifo"), (3, True, {ADDRESS}))
        for value in ([], [None], [{}], [{**good[0], "addr_info": [None]}]):
            with self.subTest(value=value), patch.object(
                trial, "command", return_value=json.dumps(value)
            ), self.assertRaises(ValueError):
                trial.observe("fifo")

    def exercise(self, observations, command_error=None):
        with patch.object(
            trial, "discover_interfaces", return_value=IDENTITY
        ), patch.object(
            trial, "observe", side_effect=observations
        ), patch.object(
            trial, "command", side_effect=command_error
        ) as command, contextlib.redirect_stdout(
            io.StringIO()
        ):
            error = None
            try:
                trial.check(ipaddress.IPv4Interface(ADDRESS))
            except BaseException as exc:
                error = exc
        return error, [call.args for call in command.call_args_list]

    def test_down_unaddressed_link_is_restored(self):
        before, during = (3, False, set()), (3, True, {ADDRESS})
        error, commands = self.exercise([before, during, during, before])
        self.assertIsNone(error)
        self.assertEqual(
            commands,
            [
                ("address", "add", ADDRESS, "dev", "fifo", "noprefixroute"),
                ("link", "set", "dev", "fifo", "up"),
                ("address", "del", ADDRESS, "dev", "fifo"),
                ("link", "set", "dev", "fifo", "down"),
            ],
        )

    def test_preexisting_address_and_up_state_are_not_changed(self):
        before = (3, True, {ADDRESS, "10.0.0.2/24"})
        error, commands = self.exercise([before] * 4)
        self.assertIsNone(error)
        self.assertEqual(commands, [])

    def test_other_up_addresses_preserved_and_only_test_address_removed(self):
        before = (3, True, {"10.0.0.2/24"})
        during = (3, True, {ADDRESS, "10.0.0.2/24"})
        error, commands = self.exercise([before, during, during, before])
        self.assertIsNone(error)
        self.assertEqual(len(commands), 2)
        self.assertEqual(
            commands[1], ("address", "del", ADDRESS, "dev", "fifo")
        )

    def test_add_timeout_after_taking_effect_is_cleaned(self):
        before, during = (3, False, set()), (3, False, {ADDRESS})
        error, commands = self.exercise(
            [before, during, before],
            [subprocess.TimeoutExpired("ip", 30), None, None],
        )
        self.assertIsInstance(error, subprocess.TimeoutExpired)
        self.assertIn(("address", "del", ADDRESS, "dev", "fifo"), commands)

    def test_verification_failure_and_interrupt_still_restore(self):
        before = (3, False, set())
        for observation in ((3, True, set()), KeyboardInterrupt()):
            with self.subTest(observation=observation):
                error, commands = self.exercise(
                    [before, observation, before, before]
                )
                self.assertIsNotNone(error)
                self.assertIn(("link", "set", "dev", "fifo", "down"), commands)

    def test_changed_identity_is_not_modified_during_cleanup(self):
        error, commands = self.exercise(
            [(3, False, set()), (3, True, {ADDRESS}), (9, True, {ADDRESS})]
        )
        self.assertIsInstance(error, ValueError)
        self.assertEqual(len(commands), 2)

    def test_cleanup_delete_failure_still_attempts_link_restoration(self):
        before, during = (3, False, set()), (3, True, {ADDRESS})
        error, commands = self.exercise(
            [before, during, during, before],
            [None, None, ValueError("delete failed"), None],
        )
        self.assertRegex(str(error), "cleanup failed")
        self.assertEqual(commands[-1], ("link", "set", "dev", "fifo", "down"))

    def test_existing_down_addresses_or_conflicting_prefix_prevent_changes(
        self,
    ):
        for before in (
            (3, False, {"10.0.0.2/24"}),
            (3, True, {"192.168.100.2/24"}),
        ):
            with self.subTest(before=before):
                error, commands = self.exercise([before])
                self.assertIsInstance(error, ValueError)
                self.assertEqual(commands, [])

    def test_missing_or_ambiguous_driver_identity_prevents_changes(self):
        for identities in ({}, {**IDENTITY, "second": IDENTITY["fifo"]}):
            with patch.object(
                trial, "discover_interfaces", return_value=identities
            ), patch.object(trial, "command") as command, self.assertRaises(
                ValueError
            ):
                trial.check(ipaddress.IPv4Interface(ADDRESS))
            command.assert_not_called()

    def test_unrestored_state_is_failure(self):
        before, during = (3, False, set()), (3, True, {ADDRESS})
        error, _ = self.exercise([before, during, during, during])
        self.assertRegex(str(error), "not restored")


if __name__ == "__main__":
    unittest.main()
