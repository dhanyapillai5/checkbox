# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise completion policy without cloud-init or network hardware."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bin/bluefield_cloud_init.py"
SPEC = importlib.util.spec_from_file_location("bluefield_cloud_init", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(SCRIPT.parent)] + sys.path):
    SPEC.loader.exec_module(helper)

HEALTHY = {"status": "done", "errors": [], "extended_status": "done"}
RENAME = (
    "Failed to rename devices: Failed to apply network config names: "
    "[nic not present] Cannot rename mac=a0:88:c2:08:0e:37 to p1, not available."
)
EVENT = {
    "name": "init-local/check-cache",
    "origin": "cloudinit",
    "event_type": "start",
}
WARNING = (
    "Failed posting event: "
    + json.dumps(EVENT)
    + (
        ". This was caused by: HTTPConnectionPool(host='10.239.8.11', port=5248): "
        "/MAAS/metadata/status/test (Failed to establish a new connection: "
        "[Errno 101] Network is unreachable)"
    )
)
REPORTING = dict(
    HEALTHY,
    datasource="maas",
    detail="DataSourceMAAS [http://10.239.8.11:5248/MAAS/metadata/]",
    extended_status="degraded done",
)


class CloudInitTests(unittest.TestCase):
    def run_check(
        self,
        details=HEALTHY,
        status=0,
        wait=0,
        datasource="maas",
        expected="maas",
        error=None,
    ):
        responses = [
            subprocess.CompletedProcess([], code, text, "")
            for code, text in (
                (wait, "done"),
                (status, json.dumps(details)),
                (0, datasource),
            )
        ]
        output = io.StringIO()
        with patch.dict(
            os.environ, {"BLUEFIELD_EXPECTED_DATASOURCE": expected}
        ), patch.object(
            helper.subprocess, "run", side_effect=error or responses
        ) as query, contextlib.redirect_stdout(
            output
        ), contextlib.redirect_stderr(
            output
        ):
            result = helper.main()
        return result, output.getvalue(), query

    def test_completion_and_bounded_commands(self):
        result, _, query = self.run_check()
        self.assertEqual(result, 0)
        self.assertEqual(
            [c.kwargs["timeout"] for c in query.call_args_list], [120, 30, 30]
        )
        self.assertEqual(self.run_check(datasource="nocloud")[0], 1)
        self.assertEqual(self.run_check(wait=1)[0], 1)
        for state in ("running", "disabled", "error", "not run"):
            self.assertEqual(self.run_check(dict(HEALTHY, status=state))[0], 1)
        self.assertEqual(self.run_check(status=2)[0], 1)

    def test_warnings_require_enforced_maas_configuration(self):
        for message, guard in (
            (RENAME, "recovered_rename"),
            (WARNING, "management_ready"),
        ):
            details = dict(
                REPORTING, recoverable_errors={"WARNING": [message, message]}
            )
            details["init"] = {"recoverable_errors": {"WARNING": [message]}}
            for ready in (True, False):
                with patch.object(helper, guard, return_value=ready) as check:
                    result, output, _ = self.run_check(details, 2, 2)
                self.assertEqual(result, 0 if ready else 1)
                check.assert_called_once_with(
                    *([RENAME] if guard == "recovered_rename" else [])
                )
                if ready:
                    self.assertIn("WARNING:", output)

    def test_unknown_and_fatal_issues_cannot_be_excused(self):
        for extra in (
            {"errors": ["fatal"]},
            {"init": {"errors": ["user-data failed"]}},
            {"recoverable_errors": {"WARNING": ["netplan failed"]}},
            {"recoverable_errors": {"ERROR": [RENAME]}},
            {"recoverable_errors": {"CRITICAL": [WARNING]}},
        ):
            details = dict(REPORTING, recoverable_errors={"WARNING": [RENAME]})
            details.update(extra)
            with patch.object(helper, "verify_deployment_network") as network:
                self.assertEqual(self.run_check(details, 2, 2)[0], 1)
                network.assert_not_called()

    def test_rename_identity_must_be_present_in_verified_intent(self):
        with patch.object(
            helper,
            "verify_deployment_network",
            return_value={("a0:88:c2:08:0e:37", "p1")},
        ):
            self.assertTrue(helper.recovered_rename(RENAME))
            self.assertFalse(
                helper.recovered_rename(RENAME.replace("p1", "p2"))
            )
        with patch.object(
            helper,
            "verify_deployment_network",
            side_effect=ValueError("configuration mismatch"),
        ):
            details = dict(REPORTING, recoverable_errors={"WARNING": [RENAME]})
            self.assertNotEqual(self.run_check(details, 2, 2)[0], 0)

    def test_reporting_rejects_late_wrong_endpoint_or_cause(self):
        for message in (
            WARNING.replace("init-local/check-cache", "modules-final"),
            WARNING.replace("host='10.239.8.11'", "host='other'"),
            WARNING.replace("Network is unreachable", "refused"),
            "Failed posting event: invalid JSON",
        ):
            self.assertFalse(helper.reporting_warning(message, REPORTING))

    def test_reporting_guard_requires_configured_address_and_default_route(
        self,
    ):
        network = sys.modules["bluefield_network_config"]
        for profile in (
            {"addresses": [], "routes": [{"to": "default"}]},
            {"addresses": ["192.0.2.10/24"], "routes": []},
        ):
            with patch.object(network, "load_config", return_value=[profile]):
                with self.assertRaises(ValueError):
                    helper.management_ready()
        profile = {
            "addresses": ["192.0.2.10/24"],
            "routes": [{"to": "default"}],
        }
        with patch.object(
            network, "load_config", return_value=[profile]
        ), patch.object(
            helper,
            "verify_deployment_network",
            return_value={("00:11:22:33:44:55", "oob")},
        ):
            self.assertTrue(helper.management_ready())

    def test_invalid_inputs_and_collection_failures(self):
        for details in (
            [],
            {},
            {"status": "done", "errors": "bad"},
            dict(HEALTHY, recoverable_errors={"WARNING": "bad"}),
        ):
            self.assertEqual(self.run_check(details)[0], 2)
        result, _, query = self.run_check(expected="")
        self.assertEqual(result, 2)
        query.assert_not_called()
        self.assertEqual(
            self.run_check(error=FileNotFoundError("missing"))[0], 2
        )
        result, output, _ = self.run_check(
            error=subprocess.TimeoutExpired(
                "cloud-init", 120, output="still running", stderr="diagnostic"
            )
        )
        self.assertEqual(result, 1)
        self.assertIn("diagnostic", output)


if __name__ == "__main__":
    unittest.main()
