# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for read-only required-module assertions."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "bluefield_modules.py"
SPEC = importlib.util.spec_from_file_location("bluefield_modules", SCRIPT)
bluefield_modules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bluefield_modules)

LOADED = (
    "mlx5_core 3145728 2 mlx5_fwctl,mlx5_ib Live 0x0\n"
    "mlx5_ib 655360 0 - Live 0x0\n"
    "other_module 16384 0 - Live 0x0\n"
)


class RequiredModuleTests(unittest.TestCase):
    def run_check(
        self, required="mlx5_core mlx5_ib", loaded=LOADED, error=None
    ):
        environment = (
            {}
            if required is None
            else {"BLUEFIELD_REQUIRED_MODULES": required}
        )
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(
                bluefield_modules.Path,
                "read_text",
                return_value=loaded,
                side_effect=error,
            ) as read:
                with contextlib.redirect_stdout(output):
                    with contextlib.redirect_stderr(output):
                        status = bluefield_modules.main()
        return status, output.getvalue(), read

    def test_required_modules_pass_with_extra_modules(self):
        status, output, _ = self.run_check()
        self.assertEqual(status, 0)
        self.assertIn("PASS: required module mlx5_core is loaded", output)
        self.assertIn("PASS: required module mlx5_ib is loaded", output)

    def test_missing_modules_are_all_reported_alongside_matches(self):
        status, output, _ = self.run_check(
            required="mlx5_core missing_one missing_two"
        )
        self.assertEqual(status, 1)
        self.assertIn("PASS: required module mlx5_core is loaded", output)
        self.assertIn(
            "FAIL: required module missing_one is not loaded", output
        )
        self.assertIn(
            "FAIL: required module missing_two is not loaded", output
        )

    def test_module_name_must_match_first_column_exactly(self):
        for required in ["mlx5", "mlx5_fwctl", "MLX5_CORE"]:
            with self.subTest(required=required):
                status, _, _ = self.run_check(required=required)
                self.assertEqual(status, 1)

    def test_empty_module_state_fails_required_assertions(self):
        status, output, _ = self.run_check(loaded="\n")
        self.assertEqual(status, 1)
        self.assertIn("mlx5_core is not loaded", output)
        self.assertIn("mlx5_ib is not loaded", output)

    def test_missing_empty_or_invalid_expectations_fail_before_reading(self):
        for required in [None, "", " \n", "mlx5-core", "../mlx5_ib", "mlx5_*"]:
            with self.subTest(required=required):
                status, output, read = self.run_check(required=required)
                self.assertEqual(status, 2)
                self.assertIn("BLUEFIELD_REQUIRED_MODULES", output)
                read.assert_not_called()

    def test_whitespace_separated_names_and_duplicates_are_supported(self):
        status, output, _ = self.run_check(
            required=" mlx5_core\tmlx5_ib\nmlx5_core "
        )
        self.assertEqual(status, 0)
        self.assertEqual(output.count("mlx5_core"), 1)

    def test_unreadable_module_state_is_an_error(self):
        status, output, _ = self.run_check(error=PermissionError("denied"))
        self.assertEqual(status, 2)
        self.assertIn("cannot read /proc/modules", output)


if __name__ == "__main__":
    unittest.main()
