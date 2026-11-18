# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Exercise PCI assertions against synthetic sysfs trees, without hardware."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "bluefield_pci.py"
SPEC = importlib.util.spec_from_file_location("bluefield_pci", SCRIPT)
bluefield_pci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bluefield_pci)

ADDRESS = "0000:03:00.0"
ROW = ADDRESS + "\t15b3\ta2dc\tmlx5_core\n"
EXPECTED = {ADDRESS: ("15b3", "a2dc", "mlx5_core")}


class PciExpectationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.devices = self.root / "devices"
        self.devices.mkdir()
        self.inventory = self.root / "pci.tsv"
        self.inventory.write_text(ROW)

    def add_device(
        self, address=ADDRESS, vendor="15b3", device="a2dc", driver="mlx5_core"
    ):
        path = self.devices / address
        path.mkdir()
        (path / "vendor").write_text("0x" + vendor + "\n")
        (path / "device").write_text("0x" + device + "\n")
        if driver:
            (path / "driver").symlink_to("../../../drivers/" + driver)
        return path

    def check(self, expected=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = bluefield_pci.check_devices(
                EXPECTED if expected is None else expected, self.devices
            )
        return status, output.getvalue()

    def test_exact_identity_and_binding_pass_allowing_extra_devices(self):
        self.add_device()
        self.add_device("0000:04:00.0", driver="other_driver")
        self.assertEqual(
            bluefield_pci.read_expectations(self.inventory), EXPECTED
        )
        status, output = self.check()
        self.assertEqual(status, 0)
        self.assertIn("Observed: " + ADDRESS + " 15b3 a2dc mlx5_core", output)

    def test_missing_device_fails(self):
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertIn("is missing", output)

    def test_wrong_vendor_device_or_driver_fails(self):
        self.add_device()
        for identity in [
            ("1234", "a2dc", "mlx5_core"),
            ("15b3", "1234", "mlx5_core"),
            ("15b3", "a2dc", "vfio-pci"),
        ]:
            with self.subTest(identity=identity):
                status, output = self.check({ADDRESS: identity})
                self.assertEqual(status, 1)
                self.assertIn("differs from expectation", output)

    def test_unbound_device_fails(self):
        self.add_device(driver=None)
        status, output = self.check()
        self.assertEqual(status, 1)
        self.assertIn("unbound", output)

    def test_reports_all_expected_devices(self):
        self.add_device()
        expected = dict(EXPECTED)
        expected["0000:04:00.0"] = EXPECTED[ADDRESS]
        status, output = self.check(expected)
        self.assertEqual(status, 1)
        self.assertIn("PASS:", output)
        self.assertIn("0000:04:00.0 is missing", output)

    def test_invalid_empty_duplicate_or_incomplete_input_is_rejected(self):
        for text in [
            "",
            ROW + ROW,
            "invalid\n",
            ROW.replace("0000:", ""),
            ROW.replace("15b3", "0x15b3"),
            ROW.replace("a2dc", "*"),
            ROW.replace("mlx5_core", ""),
            ROW.replace("03:00.0", "03:20.0"),
        ]:
            with self.subTest(text=text):
                self.inventory.write_text(text)
                with self.assertRaises(ValueError):
                    bluefield_pci.read_expectations(self.inventory)

    def test_unreadable_sysfs_cannot_pass(self):
        self.add_device().joinpath("vendor").unlink()
        with self.assertRaises(OSError):
            self.check()

    def test_missing_input_or_observation_errors_return_two(self):
        for source in ["", str(self.root / "absent.tsv")]:
            with self.subTest(source=source):
                with patch.dict(
                    os.environ, {"BLUEFIELD_EXPECTED_PCI": source}
                ):
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(bluefield_pci.main(), 2)
        with patch.dict(
            os.environ, {"BLUEFIELD_EXPECTED_PCI": str(self.inventory)}
        ):
            with patch.object(
                bluefield_pci,
                "check_devices",
                side_effect=PermissionError("denied"),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(bluefield_pci.main(), 2)


if __name__ == "__main__":
    unittest.main()
