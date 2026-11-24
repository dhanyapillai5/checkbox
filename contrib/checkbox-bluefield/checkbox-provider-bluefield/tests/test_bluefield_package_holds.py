# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for independent required-hold expectations."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = (
    Path(__file__).resolve().parents[1] / "bin" / "bluefield_package_holds.py"
)
SPEC = importlib.util.spec_from_file_location(
    "bluefield_package_holds", SCRIPT
)
holds = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(holds)


class PackageHoldTests(unittest.TestCase):
    def run_check(
        self,
        required="kernel-test stack-test",
        actual="kernel-test\nstack-test\n",
        returncode=0,
        error=None,
    ):
        output = io.StringIO()
        with patch.dict(
            os.environ, {"BLUEFIELD_REQUIRED_HOLDS": required}, clear=True
        ), patch.object(holds.subprocess, "run") as query:
            query.return_value = subprocess.CompletedProcess(
                [], returncode, actual, "query diagnostic"
            )
            query.side_effect = error
            with contextlib.redirect_stdout(output):
                with contextlib.redirect_stderr(output):
                    status = holds.main()
        return status, output.getvalue(), query

    def test_required_subset_allows_extra_holds(self):
        status, output, query = self.run_check(
            actual="stack-test\nkernel-test\nextra-test:arm64\n"
        )
        self.assertEqual(status, 0)
        self.assertIn("PASS: kernel-test is held", output)
        self.assertIn("extra-test:arm64", output)
        self.assertEqual(query.call_args.args[0], ["apt-mark", "showhold"])
        self.assertEqual(query.call_args.kwargs["timeout"], 30)
        self.assertEqual(query.call_args.kwargs["env"]["LC_ALL"], "C")

    def test_missing_holds_and_empty_observation_fail(self):
        for actual in ["kernel-test\n", "", "other-kernel-test\n"]:
            with self.subTest(actual=actual):
                status, output, _ = self.run_check(actual=actual)
                self.assertEqual(status, 1)
                self.assertIn("FAIL: stack-test is not held", output)

    def test_missing_invalid_or_duplicate_expectations_fail_before_query(self):
        for required in ["", " ", "kernel-test kernel-test", "*", "--help"]:
            with self.subTest(required=required):
                status, _, query = self.run_check(required=required)
                self.assertEqual(status, 2)
                query.assert_not_called()

    def test_query_errors_cannot_pass_even_with_matching_output(self):
        status, output, _ = self.run_check(returncode=1)
        self.assertEqual(status, 2)
        self.assertIn("query diagnostic", output)
        for error in [
            FileNotFoundError("apt-mark"),
            subprocess.TimeoutExpired("apt-mark", 30),
        ]:
            with self.subTest(error=error):
                self.assertEqual(self.run_check(error=error)[0], 2)

    def test_malformed_observations_fail(self):
        for actual in ["kernel-test\nkernel-test\n", "bad/name\n"]:
            with self.subTest(actual=actual):
                self.assertEqual(self.run_check(actual=actual)[0], 2)


if __name__ == "__main__":
    unittest.main()
