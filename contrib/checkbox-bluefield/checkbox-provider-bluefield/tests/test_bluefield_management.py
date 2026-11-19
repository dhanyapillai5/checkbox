# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Test management discovery using synthetic sysfs trees, without hardware."""

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
    Path(__file__).resolve().parents[1] / "bin" / "bluefield_management.py"
)
SPEC = importlib.util.spec_from_file_location("bluefield_management", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)

EXPECTED = {
    "oob": {"driver": "mlxbf_gige"},
    "tmfifo": {"driver": "virtio_net", "parent_driver": "bf-tmfifo"},
}


class ManagementInterfaceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.net = self.root / "net"
        self.net.mkdir()
        self.source = self.root / "expected.json"
        self.source.write_text(json.dumps(EXPECTED))
        (self.net / "lo").mkdir()

    def add_interface(self, name, driver, parent_driver=None):
        parent = self.root / (name + "-parent")
        parent.mkdir()
        if parent_driver:
            (parent / "driver").symlink_to("/drivers/" + parent_driver)
        device = parent / "device"
        device.mkdir()
        if driver:
            (device / "driver").symlink_to("/drivers/" + driver)
        interface = self.net / name
        interface.mkdir()
        (interface / "device").symlink_to(device)

    def check(self, expected=EXPECTED):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = helper.check_interfaces(expected, self.net)
        return status, output.getvalue()

    def test_arbitrary_names_match_and_unrelated_virtio_is_not_tmfifo(self):
        self.add_interface("renamed_oob", "mlxbf_gige")
        self.add_interface("renamed_fifo", "virtio_net", "bf-tmfifo")
        self.add_interface("other_virtio", "virtio_net", "other-parent")
        self.assertEqual(helper.read_expectations(self.source), EXPECTED)
        status, output = self.check()
        self.assertEqual(status, 0)
        self.assertIn("oob interface renamed_oob is present", output)
        self.assertIn("tmfifo interface renamed_fifo is present", output)

    def test_virtio_without_correct_parent_does_not_match(self):
        self.add_interface("other_virtio", "virtio_net", "wrong-parent")
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertIn("tmfifo expected one interface; found 0", output)

    def test_missing_and_ambiguous_roles_fail(self):
        self.add_interface("oob_a", "mlxbf_gige")
        self.add_interface("oob_b", "mlxbf_gige")
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertIn("oob expected one interface; found 2", output)
        self.assertIn("tmfifo expected one interface; found 0", output)

    def test_unbound_device_does_not_match(self):
        self.add_interface("unbound", None)
        self.assertEqual(self.check()[0], 1)

    def test_same_interface_cannot_satisfy_two_roles(self):
        self.add_interface("oob", "mlxbf_gige")
        status, output = self.check(
            {
                "first": {"driver": "mlxbf_gige"},
                "second": {"driver": "mlxbf_gige"},
            }
        )
        self.assertEqual(status, 1)
        self.assertIn("matched more than one role", output)

    def test_invalid_expectations_are_rejected(self):
        for expected in [
            {},
            [],
            {"oob": []},
            {"": {"driver": "foo"}},
            {"oob": {}},
            {"oob": {"parent_driver": "foo"}},
            {"oob": {"driver": "foo", "name": "fixed"}},
            {"oob": {"driver": ""}},
            {"oob": {"driver": []}},
        ]:
            with self.subTest(expected=expected):
                self.source.write_text(json.dumps(expected))
                with self.assertRaises(ValueError):
                    helper.read_expectations(self.source)

    def test_broken_device_link_and_absent_sysfs_raise_errors(self):
        self.add_interface("oob", "mlxbf_gige")
        device = self.net / "oob" / "device"
        device.unlink()
        device.symlink_to(self.root / "absent")
        with self.assertRaises(OSError):
            self.check()
        with self.assertRaises(OSError):
            helper.check_interfaces(EXPECTED, self.root / "absent")

    def test_main_reports_missing_input_and_read_errors(self):
        for source in ["", str(self.root / "absent")]:
            with patch.dict(
                os.environ, {"BLUEFIELD_EXPECTED_MANAGEMENT": source}
            ):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(helper.main(), 2)
        with patch.dict(
            os.environ, {"BLUEFIELD_EXPECTED_MANAGEMENT": str(self.source)}
        ):
            with patch.object(
                helper,
                "check_interfaces",
                side_effect=PermissionError("denied"),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(helper.main(), 2)


if __name__ == "__main__":
    unittest.main()
