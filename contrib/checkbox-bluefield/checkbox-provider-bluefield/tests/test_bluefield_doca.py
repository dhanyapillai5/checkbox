# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise device identity and query/linkage failures without hardware."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin/bluefield_doca.py"
SPEC = importlib.util.spec_from_file_location("bluefield_doca", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(SCRIPT.parent)] + sys.path):
    SPEC.loader.exec_module(helper)

ADDRESSES = ["0000:03:00.0", "0000:03:00.1"]
ENUMERATION = json.dumps(
    {
        "devices": [
            {"pci_addr": a, "common": {"ibdev_name": "mlx5_" + str(i)}}
            for i, a in enumerate(ADDRESSES)
        ]
    }
)
LINKAGE = (
    "libdoca_argp.so.2 => /opt/libdoca_argp.so.2 (0x123)\n"
    "libdoca_common.so.2 => /opt/libdoca_common.so.2 (0x456)\n"
)


def capability(address, values=None):
    return json.dumps(
        {
            "devices": [
                {
                    "pci_addr": address,
                    "libraries": {
                        "common": (
                            values
                            if values is not None
                            else {"feature": "unsupported"}
                        )
                    },
                }
            ]
        }
    )


class DocaTests(unittest.TestCase):
    def run_check(self, values):
        with patch.object(
            helper, "query", side_effect=values
        ), contextlib.redirect_stdout(io.StringIO()):
            helper.check(ADDRESSES)

    def test_all_expected_devices_queried_and_unsupported_is_valid(self):
        values = [ENUMERATION] + [capability(a) for a in ADDRESSES] + [LINKAGE]
        self.run_check(values)

    def test_missing_duplicate_wrong_or_empty_responses_fail(self):
        for enumeration in (
            "{}",
            '{"devices": []}',
            json.dumps({"devices": [{"pci_addr": ADDRESSES[0]}]}),
            json.dumps({"devices": [{"pci_addr": ADDRESSES[0]}] * 2}),
        ):
            with self.assertRaises(ValueError):
                self.run_check([enumeration])
        for response in (
            capability("0000:04:00.0"),
            capability(ADDRESSES[0], {}),
            capability(ADDRESSES[0], {"feature": "unknown"}),
            "bad",
        ):
            with self.assertRaises(ValueError):
                self.run_check([ENUMERATION, response])

    def test_missing_or_unresolved_linkage_fails(self):
        for linkage in (
            "",
            LINKAGE + "other.so => not found",
            "libc.so => /lib/c",
        ):
            with self.assertRaises(ValueError):
                self.run_check(
                    [ENUMERATION]
                    + [capability(a) for a in ADDRESSES]
                    + [linkage]
                )

    def test_queries_bounded_and_nonzero_rejected(self):
        with patch.object(
            helper.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, "", "denied"),
        ) as run, contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(
            io.StringIO()
        ):
            with self.assertRaises(ValueError):
                helper.query(["tool"])
            self.assertEqual(run.call_args.kwargs["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
