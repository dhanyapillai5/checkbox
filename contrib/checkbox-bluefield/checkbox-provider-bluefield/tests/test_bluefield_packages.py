# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for candidate-based required-package checks."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "bluefield_packages.py"
SPEC = importlib.util.spec_from_file_location("bluefield_packages", SCRIPT)
bluefield_packages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bluefield_packages)

CANDIDATE = "kernel-test\t1:2.3-4\tarm64\nstack-test\t5.6\tall\n"
INSTALLED = (
    "kernel-test\t1:2.3-4\tarm64\tinstalled\n"
    "stack-test\t5.6\tall\tinstalled\n"
)


class PackageExpectationTests(unittest.TestCase):
    def run_check(
        self,
        candidate=CANDIDATE,
        actual=INSTALLED,
        required="kernel-test stack-test",
        query_error=None,
    ):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "candidate.tsv"
            inventory.write_text(candidate)
            environment = {
                "BLUEFIELD_CANDIDATE_INVENTORY": str(inventory),
                "BLUEFIELD_REQUIRED_PACKAGES": required,
            }
            output = io.StringIO()
            with patch.dict(os.environ, environment, clear=True):
                with patch.object(
                    bluefield_packages.subprocess, "run"
                ) as query:
                    query.return_value.stdout = actual
                    query.side_effect = query_error
                    with contextlib.redirect_stdout(output):
                        with contextlib.redirect_stderr(output):
                            status = bluefield_packages.main()
            return status, output.getvalue(), query

    def test_exact_matches_allow_extra_and_unselected_changed_packages(self):
        status, output, query = self.run_check(
            actual=INSTALLED + "extra-test\t9\tarm64\tinstalled\n"
        )
        self.assertEqual(status, 0)
        self.assertIn("Expected: kernel-test 1:2.3-4 arm64 installed", output)
        self.assertIn("PASS: stack-test", output)
        self.assertTrue(query.call_args.kwargs["check"])
        self.assertEqual(query.call_args.kwargs["timeout"], 30)
        status, _, _ = self.run_check(
            required="kernel-test",
            actual=INSTALLED.replace("5.6", "changed"),
        )
        self.assertEqual(status, 0)

    def test_missing_version_architecture_and_status_mismatches_fail(self):
        for actual, diagnostic in [
            (INSTALLED.splitlines(True)[1], "kernel-test missing"),
            (INSTALLED.replace("1:2.3-4", "2.3-4"), "2.3-4"),
            (INSTALLED.replace("arm64", "amd64"), "amd64"),
            (INSTALLED.replace("installed", "unpacked"), "unpacked"),
            (INSTALLED.replace("installed", "config-files"), "config-files"),
        ]:
            with self.subTest(actual=actual):
                status, output, _ = self.run_check(actual=actual)
                self.assertEqual(status, 1)
                self.assertIn("FAIL: observed", output)
                self.assertIn(diagnostic, output)

    def test_invalid_or_ambiguous_candidate_fails_before_query(self):
        for candidate in [
            "",
            "invalid\n",
            CANDIDATE + CANDIDATE,
            CANDIDATE.replace("kernel-test", "other-test"),
            CANDIDATE + "kernel-test\t1:2.3-4\tamd64\n",
            CANDIDATE.replace("1:2.3-4", "bad version"),
            CANDIDATE.replace("arm64", ""),
        ]:
            with self.subTest(candidate=candidate):
                status, output, query = self.run_check(candidate=candidate)
                self.assertEqual(status, 2)
                self.assertIn("FAIL:", output)
                query.assert_not_called()

    def test_missing_invalid_or_duplicate_required_names_fail(self):
        for required in ["", " ", "kernel-test kernel-test", "kernel-test:* "]:
            with self.subTest(required=required):
                status, _, query = self.run_check(required=required)
                self.assertEqual(status, 2)
                query.assert_not_called()

    def test_missing_or_unreadable_inventory_fails(self):
        for inventory in ["", "/no-such-bluefield-directory/candidate.tsv"]:
            with self.subTest(inventory=inventory):
                with patch.dict(
                    os.environ,
                    {
                        "BLUEFIELD_CANDIDATE_INVENTORY": inventory,
                        "BLUEFIELD_REQUIRED_PACKAGES": "kernel-test",
                    },
                    clear=True,
                ):
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(bluefield_packages.main(), 2)

    def test_query_errors_or_malformed_output_cannot_pass(self):
        for error in [
            FileNotFoundError("dpkg-query"),
            subprocess.CalledProcessError(1, "dpkg-query"),
            subprocess.TimeoutExpired("dpkg-query", 30),
        ]:
            with self.subTest(error=error):
                status, _, _ = self.run_check(query_error=error)
                self.assertEqual(status, 2)
        for actual in ["", "bad\n", INSTALLED + INSTALLED]:
            with self.subTest(actual=actual):
                status, _, _ = self.run_check(actual=actual)
                self.assertEqual(status, 2)


if __name__ == "__main__":
    unittest.main()
