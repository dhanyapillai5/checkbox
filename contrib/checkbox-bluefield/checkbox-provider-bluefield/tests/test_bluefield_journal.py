# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Verify journal attachment selection, boot identity and collection errors."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
SPEC = importlib.util.spec_from_file_location(
    "journal", BIN / "bluefield_journal.py"
)
journal = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(BIN)] + sys.path):
    SPEC.loader.exec_module(journal)


class JournalAttachmentTests(unittest.TestCase):
    def run_check(
        self,
        scope="kernel",
        required="ovsdb.service:active:running",
        boot="2a1e209e-a643-437a-8909-afaa376aa7ba\n",
        error=None,
        returncode=0,
    ):
        output = io.StringIO()
        with patch.dict(
            os.environ, {"BLUEFIELD_REQUIRED_SERVICES": required}, clear=True
        ), patch.object(Path, "read_text", return_value=boot), patch.object(
            journal.subprocess, "run", side_effect=error
        ) as query, contextlib.redirect_stdout(
            output
        ), contextlib.redirect_stderr(
            output
        ):
            query.return_value.returncode = returncode
            status = journal.main([scope])
        return status, query, output.getvalue()

    def test_kernel_journal_pinned_to_current_boot_and_streamed(self):
        status, query, output = self.run_check()
        self.assertEqual(status, 0)
        self.assertIn(
            "--boot=2a1e209ea643437a8909afaa376aa7ba", query.call_args.args[0]
        )
        self.assertIn("--dmesg", query.call_args.args[0])
        self.assertNotIn("--unit", query.call_args.args[0])
        self.assertNotIn("capture_output", query.call_args.kwargs)
        self.assertEqual(query.call_args.kwargs["timeout"], 60)
        self.assertIn("Boot ID: 2a1e209ea643437a8909afaa376aa7ba", output)

    def test_compact_boot_identity_is_preserved(self):
        status, query, _ = self.run_check(
            boot="2a1e209ea643437a8909afaa376aa7ba\n"
        )
        self.assertEqual(status, 0)
        self.assertIn(
            "--boot=2a1e209ea643437a8909afaa376aa7ba", query.call_args.args[0]
        )

    def test_service_units_come_only_from_explicit_input(self):
        status, query, _ = self.run_check(
            scope="services",
            required="one.service:active:exited two.service:active:running",
        )
        self.assertEqual(status, 0)
        self.assertEqual(
            query.call_args.args[0][-4:],
            ["--unit", "one.service", "--unit", "two.service"],
        )
        self.assertNotIn("--dmesg", query.call_args.args[0])

    def test_missing_invalid_or_duplicate_service_input_prevents_collection(
        self,
    ):
        for value in (
            "",
            "bad",
            "x.service:active:running x.service:active:running",
        ):
            with self.subTest(value=value):
                status, query, _ = self.run_check(
                    scope="services", required=value
                )
                self.assertEqual(status, 1)
                query.assert_not_called()

    def test_boot_identity_required(self):
        for boot in ("", "test-boot"):
            with self.subTest(boot=boot):
                status, query, _ = self.run_check(boot=boot)
                self.assertEqual(status, 1)
                query.assert_not_called()

    def test_failed_or_timed_out_collection_cannot_pass(self):
        self.assertEqual(self.run_check(returncode=1)[0], 1)
        for error in (
            FileNotFoundError(),
            subprocess.TimeoutExpired("journalctl", 60),
        ):
            with self.subTest(error=error):
                self.assertEqual(self.run_check(error=error)[0], 1)


if __name__ == "__main__":
    unittest.main()
