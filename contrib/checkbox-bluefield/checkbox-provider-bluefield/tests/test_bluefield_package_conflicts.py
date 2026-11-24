# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for candidate-based installed Conflicts assertions."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "bin"
    / "bluefield_package_conflicts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "bluefield_package_conflicts", SCRIPT
)
conflicts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(conflicts)

REFERENCE = (
    "stack-common\tstock-common (<< 1.2~)\n"
    "stack-switch\tstock-switch (<< 1.2~)\n"
)
INSTALLED = REFERENCE.replace("\n", "\tinstalled\n")


class PackageConflictsTests(unittest.TestCase):
    def run_check(
        self, reference=REFERENCE, actual=INSTALLED, returncode=0, error=None
    ):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conflicts.tsv"
            path.write_text(reference)
            output = io.StringIO()
            with patch.dict(
                os.environ,
                {"BLUEFIELD_EXPECTED_CONFLICTS": str(path)},
                clear=True,
            ), patch.object(conflicts.subprocess, "run") as query:
                query.return_value = subprocess.CompletedProcess(
                    [], returncode, actual, "query diagnostic"
                )
                query.side_effect = error
                with contextlib.redirect_stdout(output):
                    with contextlib.redirect_stderr(output):
                        status = conflicts.main()
            return status, output.getvalue(), query

    def test_exact_installed_fields_match(self):
        status, output, query = self.run_check()
        self.assertEqual(status, 0)
        self.assertIn("Expected stack-common: Conflicts:", output)
        self.assertIn("PASS: stack-switch", output)
        self.assertIn("stock-common (<< 1.2~)\tinstalled", output)
        self.assertEqual(
            query.call_args.args[0],
            [
                "dpkg-query",
                "-W",
                "-f=${Package}\t${Conflicts}\t${db:Status-Status}\n",
                "stack-common",
                "stack-switch",
            ],
        )
        self.assertEqual(query.call_args.kwargs["timeout"], 30)
        self.assertEqual(query.call_args.kwargs["env"]["LC_ALL"], "C")

    def test_candidate_values_are_not_hardcoded(self):
        reference = "other-stack\tother-stock (>= 9), incompatible\n"
        status, _, _ = self.run_check(
            reference=reference,
            actual=reference.replace("\n", "\tinstalled\n"),
        )
        self.assertEqual(status, 0)

    def test_missing_changed_unversioned_extra_conflicts_and_status_fail(self):
        for actual in [
            INSTALLED.splitlines(True)[1],
            INSTALLED.replace("1.2~", "2.0~"),
            INSTALLED.replace(" (<< 1.2~)", ""),
            INSTALLED.replace("<<", "<="),
            INSTALLED.replace("1.2~)", "1.2~), extra-conflict"),
            INSTALLED.replace("stock-common (<< 1.2~)", ""),
            INSTALLED.replace("installed", "unpacked"),
            INSTALLED.replace("installed", "config-files"),
        ]:
            with self.subTest(actual=actual):
                status, output, _ = self.run_check(actual=actual)
                self.assertEqual(status, 1)
                self.assertIn("FAIL:", output)

    def test_invalid_empty_duplicate_reference_fails_before_query(self):
        for reference in [
            "",
            "bad\n",
            REFERENCE + REFERENCE,
            "stack-common\t\n",
            "--help\tstock\n",
            "stack-*\tstock\n",
            "stack-common\t stock\n",
            "stack-common\tstock\textra\n",
        ]:
            with self.subTest(reference=reference):
                status, _, query = self.run_check(reference=reference)
                self.assertEqual(status, 2)
                query.assert_not_called()

    def test_missing_relative_unreadable_or_undecodable_reference_fails(self):
        for path in ["", "relative.tsv", "/no-such-bluefield/conflicts.tsv"]:
            with self.subTest(path=path), patch.dict(
                os.environ, {"BLUEFIELD_EXPECTED_CONFLICTS": path}, clear=True
            ), patch.object(conflicts.subprocess, "run") as query:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(conflicts.main(), 2)
                query.assert_not_called()
        with patch.dict(
            os.environ, {"BLUEFIELD_EXPECTED_CONFLICTS": "/bad.tsv"}
        ), patch.object(Path, "read_text", side_effect=UnicodeError("bad")):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(conflicts.main(), 2)

    def test_failed_queries_and_malformed_observations_cannot_pass(self):
        status, output, _ = self.run_check(returncode=1)
        self.assertEqual(status, 2)
        self.assertIn("query diagnostic", output)
        for error in [
            FileNotFoundError("dpkg-query"),
            subprocess.TimeoutExpired("dpkg-query", 30),
        ]:
            with self.subTest(error=error):
                self.assertEqual(self.run_check(error=error)[0], 2)
        for actual in ["", "bad\n", INSTALLED + INSTALLED]:
            with self.subTest(actual=actual):
                self.assertEqual(self.run_check(actual=actual)[0], 2)


if __name__ == "__main__":
    unittest.main()
