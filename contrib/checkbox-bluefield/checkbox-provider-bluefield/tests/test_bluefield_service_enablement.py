# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for independent service enablement policy."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = (
    Path(__file__).resolve().parents[1] / "bin/bluefield_service_enablement.py"
)
SPEC = importlib.util.spec_from_file_location("enablement", SCRIPT)
enablement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(enablement)


class EnablementTests(unittest.TestCase):
    def run_check(self, expected, results):
        output = io.StringIO()
        with patch.dict(
            os.environ, {"BLUEFIELD_SERVICE_ENABLEMENT": expected}, clear=True
        ), patch.object(
            enablement.subprocess, "run", side_effect=results
        ) as query:
            with contextlib.redirect_stdout(output):
                with contextlib.redirect_stderr(output):
                    status = enablement.main()
        return status, output.getvalue(), query

    def result(self, state, code=0, stderr=""):
        return subprocess.CompletedProcess([], code, state + "\n", stderr)

    def test_native_sysv_and_disabled_timer_match(self):
        status, output, query = self.run_check(
            "native.service:enabled legacy.service:enabled "
            "daily.timer:disabled",
            [
                self.result("enabled"),
                self.result("enabled", stderr="Redirecting to sysv-install"),
                self.result("disabled", 1),
            ],
        )
        self.assertEqual(status, 0)
        self.assertIn("Redirecting to sysv-install", output)
        self.assertIn("PASS: daily.timer", output)
        self.assertEqual(
            query.call_args_list[1].args[0],
            ["systemctl", "is-enabled", "legacy.service"],
        )
        self.assertEqual(query.call_args.kwargs["timeout"], 30)
        self.assertEqual(query.call_args.kwargs["env"]["LC_ALL"], "C")

    def test_wrong_missing_masked_static_and_query_failure_cannot_pass(self):
        for state, code in [
            ("enabled", 0),
            ("not-found", 4),
            ("masked", 1),
            ("static", 0),
            ("disabled", 4),
            ("", 1),
            ("disabled\nenabled", 1),
        ]:
            with self.subTest(state=state, code=code):
                status, _, _ = self.run_check(
                    "test.service:disabled", [self.result(state, code)]
                )
                self.assertEqual(status, 1)

    def test_disabled_does_not_satisfy_enabled(self):
        self.assertEqual(
            self.run_check(
                "test.service:enabled", [self.result("disabled", 1)]
            )[0],
            1,
        )

    def test_invalid_or_empty_input_fails_before_query(self):
        for value in (
            "",
            "bad",
            "x.service:masked",
            "x.service:enabled x.service:disabled",
            "--help.service:enabled",
            "x.socket:enabled",
        ):
            with self.subTest(value=value):
                status, _, query = self.run_check(value, [])
                self.assertEqual(status, 2)
                query.assert_not_called()

    def test_missing_tool_and_timeout_fail(self):
        for error in (
            FileNotFoundError(),
            subprocess.TimeoutExpired("cmd", 30),
        ):
            with self.subTest(error=error):
                self.assertEqual(
                    self.run_check("test.service:enabled", error)[0], 2
                )


if __name__ == "__main__":
    unittest.main()
