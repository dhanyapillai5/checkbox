# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for candidate-based running boot argument assertions."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin/bluefield_boot_args.py"
SPEC = importlib.util.spec_from_file_location("bluefield_boot_args", SCRIPT)
boot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(boot)


class BootArgumentTests(unittest.TestCase):
    def run_check(
        self,
        required="debug console=one console=two",
        forbidden="net.ifnames=0 biosdevname=0",
        actual="root=UUID=example console=two debug console=one ro\n",
        error=None,
    ):
        output = io.StringIO()
        with patch.dict(
            os.environ,
            {
                "BLUEFIELD_REQUIRED_BOOT_ARGS": required,
                "BLUEFIELD_FORBIDDEN_BOOT_ARGS": forbidden,
            },
            clear=True,
        ), patch.object(
            Path, "read_text", return_value=actual, side_effect=error
        ) as read:
            with contextlib.redirect_stdout(output):
                with contextlib.redirect_stderr(output):
                    status = boot.main()
        return status, output.getvalue(), read

    def test_required_subset_and_multiple_consoles_allow_extra_arguments(self):
        status, output, _ = self.run_check()
        self.assertEqual(status, 0)
        self.assertIn("PASS: required present console=one", output)
        self.assertIn("PASS: forbidden absent net.ifnames=0", output)
        self.assertIn("root=UUID=example", output)

    def test_missing_or_changed_argument_fails(self):
        for actual in ["console=one console=two", "debug console=one-more"]:
            with self.subTest(actual=actual):
                status, output, _ = self.run_check(actual=actual)
                self.assertEqual(status, 1)
                self.assertIn("FAIL: missing", output)

    def test_forbidden_exact_tokens_fail(self):
        for arg in ("net.ifnames=0", "biosdevname=0"):
            with self.subTest(arg=arg):
                status, output, _ = self.run_check(
                    actual="debug console=one console=two " + arg
                )
                self.assertEqual(status, 1)
                self.assertIn("FAIL: forbidden present " + arg, output)

    def test_forbidden_values_are_not_substring_matches(self):
        status, _, _ = self.run_check(
            required="other=9", actual="other=9 net.ifnames=1 biosdevname=1"
        )
        self.assertEqual(status, 0)

    def test_optional_forbidden_list_can_be_empty(self):
        self.assertEqual(self.run_check(forbidden="")[0], 0)

    def test_missing_invalid_duplicate_or_overlapping_inputs_fail_before_read(
        self,
    ):
        for required, forbidden in [
            ("", ""),
            (" ", ""),
            ("debug debug", ""),
            ("debug", "bad bad"),
            ("debug", "debug"),
            ("--", ""),
            ("debug\x1b", ""),
        ]:
            with self.subTest(required=required, forbidden=forbidden):
                status, _, read = self.run_check(
                    required=required, forbidden=forbidden
                )
                self.assertEqual(status, 2)
                read.assert_not_called()

    def test_empty_multiline_or_unreadable_observation_fails(self):
        for actual in ("", "\n", "debug\nconsole=one\n"):
            with self.subTest(actual=actual):
                self.assertEqual(self.run_check(actual=actual)[0], 2)
        for error in (FileNotFoundError(), PermissionError(), UnicodeError()):
            with self.subTest(error=error):
                self.assertEqual(self.run_check(error=error)[0], 2)

    def test_init_arguments_do_not_satisfy_kernel_expectations(self):
        self.assertEqual(
            self.run_check(required="debug", actual="ro -- debug")[0], 1
        )
        self.assertEqual(
            self.run_check(
                required="ro", forbidden="debug", actual="ro -- debug"
            )[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
