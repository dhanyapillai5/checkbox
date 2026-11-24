# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only
"""Check required running daemons and successful oneshot service states."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin/bluefield_services.py"
SPEC = importlib.util.spec_from_file_location("bluefield_services", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class ServiceTests(unittest.TestCase):
    def test_running_and_exited_require_exact_loaded_success_state(self):
        for state in ("running", "exited"):
            expected = helper.read_expectations("test.service:active:" + state)
            good = (
                "LoadState=loaded\nActiveState=active\nSubState="
                + state
                + "\nResult=success\n"
            )
            for output, code, outcome in (
                (good, 0, 0),
                (good.replace("loaded", "not-found"), 0, 1),
                (good.replace("active", "inactive"), 0, 1),
                (good.replace("success", "exit-code"), 0, 1),
                (good.replace("SubState=" + state, "SubState=dead"), 0, 1),
                ("", 0, 1),
            ):
                with patch.object(
                    helper.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [], code, output, ""
                    ),
                ) as run, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(helper.check(expected), outcome)
                    self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_invalid_missing_duplicate_expectations_rejected(self):
        for value in (
            "",
            "unit",
            "x.service:inactive:dead",
            "x:active:running",
            "x.service:active:running x.service:active:exited",
        ):
            with self.assertRaises(ValueError):
                helper.read_expectations(value)

    def test_timeout_failed_query_and_bad_output_do_not_pass(self):
        for result in (
            subprocess.TimeoutExpired("systemctl", 30),
            subprocess.CompletedProcess([], 1, "", "denied"),
            subprocess.CompletedProcess([], 0, "bad", ""),
        ):
            kwargs = (
                {"side_effect": result}
                if isinstance(result, Exception)
                else {"return_value": result}
            )
            with patch.dict(
                os.environ,
                {"BLUEFIELD_REQUIRED_SERVICES": "x.service:active:running"},
            ), patch.object(
                helper.subprocess, "run", **kwargs
            ), contextlib.redirect_stdout(
                io.StringIO()
            ), contextlib.redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(helper.main(), 1)


if __name__ == "__main__":
    unittest.main()
