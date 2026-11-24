# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for candidate-derived literal configuration settings."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = (
    Path(__file__).resolve().parents[1] / "bin/bluefield_config_settings.py"
)
SPEC = importlib.util.spec_from_file_location("settings", SCRIPT)
settings = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(settings)


class SettingTests(unittest.TestCase):
    def run_check(self, text, value="yes"):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            config.write_text(text)
            reference = Path(directory) / "expected.json"
            reference.write_text(
                json.dumps(
                    [{"file": str(config), "key": "EXAMPLE", "value": value}]
                )
            )
            output = io.StringIO()
            with patch.dict(
                os.environ,
                {"BLUEFIELD_EXPECTED_SETTINGS": str(reference)},
                clear=True,
            ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(
                output
            ):
                status = settings.main()
            return status, output.getvalue()

    def test_literal_values_quotes_comments_and_extra_settings(self):
        for text in (
            'EXAMPLE="yes"\nOTHER=no\n',
            "EXAMPLE='yes' # comment\n",
            "# EXAMPLE=no\nEXAMPLE=yes\n",
            " export EXAMPLE=yes\n",
        ):
            with self.subTest(text=text):
                status, output = self.run_check(text)
                self.assertEqual(status, 0)
                self.assertIn("EXAMPLE='yes'", output)

    def test_independent_expected_value_is_not_hardcoded(self):
        self.assertEqual(self.run_check("EXAMPLE=other", value="other")[0], 0)

    def test_wrong_missing_and_commented_out_values_fail(self):
        for text in ("EXAMPLE=no", "", "#EXAMPLE=yes", "EXAMPLE_OTHER=yes"):
            with self.subTest(text=text):
                self.assertEqual(self.run_check(text)[0], 1)

    def test_duplicates_malformed_and_nonliteral_assignments_fail(self):
        for text in (
            "EXAMPLE=yes\nEXAMPLE=no",
            'EXAMPLE="yes',
            "EXAMPLE=yes no",
            "EXAMPLE=$(command)",
            "EXAMPLE=`command`",
            "EXAMPLE=yes; command",
            "EXAMPLE=$VARIABLE",
            "EXAMPLE=yes\\\nOTHER=no",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.run_check(text)[0], 2)

    def test_invalid_reference_schema_or_duplicate_identity_fails(self):
        good = {"file": "/some/file", "key": "EXAMPLE", "value": "yes"}
        for expected in (
            [],
            {},
            [good, good],
            [{**good, "file": "relative"}],
            [{**good, "file": "/a/../b"}],
            [{**good, "key": "bad-key"}],
            [{**good, "value": True}],
            [{**good, "extra": "x"}],
        ):
            with self.subTest(expected=expected), self.assertRaises(
                ValueError
            ):
                settings.read_expectations(json.dumps(expected))

    def test_missing_relative_unreadable_invalid_or_undecodable_reference(
        self,
    ):
        for reference in ("", "relative.json", "/no-such-bluefield/reference"):
            with patch.dict(
                os.environ,
                {"BLUEFIELD_EXPECTED_SETTINGS": reference},
                clear=True,
            ), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(settings.main(), 2)
        for error in (PermissionError(), UnicodeError()):
            with patch.dict(
                os.environ, {"BLUEFIELD_EXPECTED_SETTINGS": "/expected.json"}
            ), patch.object(Path, "read_text", side_effect=error):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(settings.main(), 2)
        with self.assertRaises(ValueError):
            settings.read_expectations("invalid json")

    def test_unreadable_target_fails(self):
        reference = json.dumps(
            [{"file": "/target", "key": "EXAMPLE", "value": "yes"}]
        )
        with patch.dict(
            os.environ, {"BLUEFIELD_EXPECTED_SETTINGS": "/expected.json"}
        ), patch.object(
            Path, "read_text", side_effect=[reference, PermissionError()]
        ), contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(
            io.StringIO()
        ):
            self.assertEqual(settings.main(), 2)


if __name__ == "__main__":
    unittest.main()
