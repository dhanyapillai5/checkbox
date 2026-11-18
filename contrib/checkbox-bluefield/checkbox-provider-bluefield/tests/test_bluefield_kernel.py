# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for explicit kernel expectations and failure reporting."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "bluefield_kernel.py"
SPEC = importlib.util.spec_from_file_location("bluefield_kernel", SCRIPT)
bluefield_kernel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bluefield_kernel)


class KernelExpectationTests(unittest.TestCase):
    def run_check(self, expected, actual="test-kernel-bluefield"):
        environment = (
            {} if expected is None else {"BLUEFIELD_EXPECTED_KERNEL": expected}
        )
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(bluefield_kernel.platform, "release") as release:
                release.return_value = actual
                with contextlib.redirect_stdout(output):
                    with contextlib.redirect_stderr(output):
                        status = bluefield_kernel.main()
        return status, output.getvalue()

    def test_exact_release_passes_and_records_expectation_and_observation(
        self,
    ):
        status, output = self.run_check("test-kernel-bluefield")
        self.assertEqual(status, 0)
        self.assertIn("Expected kernel: test-kernel-bluefield", output)
        self.assertIn("Running kernel: test-kernel-bluefield", output)

    def test_different_release_fails(self):
        status, output = self.run_check("other-kernel-bluefield")
        self.assertEqual(status, 1)
        self.assertIn("Expected kernel: other-kernel-bluefield", output)
        self.assertIn("Running kernel: test-kernel-bluefield", output)

    def test_release_comparison_is_exact(self):
        status, _ = self.run_check("test-kernel")
        self.assertEqual(status, 1)

    def test_missing_empty_or_whitespace_input_is_an_error(self):
        for expected in [
            None,
            "",
            " ",
            "kernel\n",
            "kernel extra",
            "\tkernel",
        ]:
            with self.subTest(expected=expected):
                status, output = self.run_check(expected)
                self.assertEqual(status, 2)
                self.assertIn("BLUEFIELD_EXPECTED_KERNEL", output)

    def test_cli_exit_status(self):
        for expected, status in [
            (platform.release(), 0),
            (platform.release() + "-not-running", 1),
            ("", 2),
        ]:
            with self.subTest(expected=expected):
                environment = dict(
                    os.environ, BLUEFIELD_EXPECTED_KERNEL=expected
                )
                result = subprocess.run(
                    [sys.executable, str(SCRIPT)],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, status)


if __name__ == "__main__":
    unittest.main()
