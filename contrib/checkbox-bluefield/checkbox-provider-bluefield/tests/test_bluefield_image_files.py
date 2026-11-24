# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Behavioural tests for independent image file policy assertions."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin/bluefield_image_files.py"
SPEC = importlib.util.spec_from_file_location("bluefield_image_files", SCRIPT)
files = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(files)


class ImageFileTests(unittest.TestCase):
    def run_check(self, check, environment):
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True):
            with contextlib.redirect_stdout(output):
                with contextlib.redirect_stderr(output):
                    status = files.main([check])
        return status, output.getvalue()

    def test_absent_files_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [str(Path(directory) / name) for name in ("one", "two")]
            status, output = self.run_check(
                "absent", {"BLUEFIELD_ABSENT_FILES": " ".join(paths)}
            )
            self.assertEqual(status, 0)
            for path in paths:
                self.assertIn("PASS: absent " + path, output)

    def test_files_directories_and_dangling_symlinks_are_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file").touch()
            (root / "directory").mkdir()
            (root / "symlink").symlink_to(root / "missing")
            for name in ("file", "directory", "symlink"):
                with self.subTest(name=name):
                    path = str(root / name)
                    status, output = self.run_check(
                        "absent", {"BLUEFIELD_ABSENT_FILES": path}
                    )
                    self.assertEqual(status, 1)
                    self.assertIn("FAIL: present " + path, output)

    def test_invalid_absence_inputs_fail_before_observation(self):
        for value in ("", " ", "relative", "/", "/a /a", "/a/../b", "/a/./b"):
            with self.subTest(value=value), patch.object(
                Path, "lstat"
            ) as stat:
                status, _ = self.run_check(
                    "absent", {"BLUEFIELD_ABSENT_FILES": value}
                )
                self.assertEqual(status, 2)
                stat.assert_not_called()

    def test_permission_and_invalid_parent_errors_are_not_absence(self):
        for error in (PermissionError("denied"), NotADirectoryError("parent")):
            with self.subTest(error=error), patch.object(
                Path, "lstat", side_effect=error
            ):
                status, output = self.run_check(
                    "absent", {"BLUEFIELD_ABSENT_FILES": "/some/file"}
                )
                self.assertEqual(status, 2)
                self.assertIn("FAIL:", output)

    def test_release_suffix_comes_from_input_not_current_version(self):
        for suffix, release in (
            ("_candidate", "bundle-9.9_candidate\n"),
            ("_other", "bundle-1_other"),
        ):
            with self.subTest(suffix=suffix), patch.object(
                Path, "read_text", return_value=release
            ):
                status, output = self.run_check(
                    "release", {"BLUEFIELD_EXPECTED_RELEASE_SUFFIX": suffix}
                )
                self.assertEqual(status, 0)
                self.assertIn(
                    "Expected /etc/mlnx-release suffix: " + suffix, output
                )
                self.assertIn(repr(release), output)

    def test_wrong_empty_or_multiline_release_fails(self):
        for release in (
            "bundle_prod\n",
            "bundle_candidate_extra\n",
            "",
            "_candidate\n",
            "bundle_candidate\nextra\n",
            "bundle_candidate\n\n",
            "bundle_candidate \n",
        ):
            with self.subTest(release=release), patch.object(
                Path, "read_text", return_value=release
            ):
                status, _ = self.run_check(
                    "release",
                    {"BLUEFIELD_EXPECTED_RELEASE_SUFFIX": "_candidate"},
                )
                self.assertEqual(status, 1)

    def test_missing_or_invalid_suffix_fails_before_read(self):
        for suffix in ("", "candidate", "_", "_bad suffix", "_bad\n"):
            with self.subTest(suffix=suffix), patch.object(
                Path, "read_text"
            ) as read:
                status, _ = self.run_check(
                    "release", {"BLUEFIELD_EXPECTED_RELEASE_SUFFIX": suffix}
                )
                self.assertEqual(status, 2)
                read.assert_not_called()

    def test_release_read_errors_cannot_pass(self):
        for error in (FileNotFoundError(), PermissionError(), UnicodeError()):
            with self.subTest(error=error), patch.object(
                Path, "read_text", side_effect=error
            ):
                status, _ = self.run_check(
                    "release",
                    {"BLUEFIELD_EXPECTED_RELEASE_SUFFIX": "_candidate"},
                )
                self.assertEqual(status, 2)


if __name__ == "__main__":
    unittest.main()
