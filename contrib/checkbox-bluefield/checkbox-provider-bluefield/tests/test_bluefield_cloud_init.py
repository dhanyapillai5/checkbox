# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Verify cloud-init policy and bounded diagnostic collection without a DUT."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = (
    Path(__file__).resolve().parents[1] / "bin" / "bluefield_cloud_init.py"
)
SPEC = importlib.util.spec_from_file_location("bluefield_cloud_init", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(SCRIPT.parent)] + sys.path):
    SPEC.loader.exec_module(helper)

HEALTHY = {
    "status": "done",
    "extended_status": "done",
    "errors": [],
    "recoverable_errors": {},
}

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
    recoverable_errors={"WARNING": [WARNING]},
)


class CloudInitTests(unittest.TestCase):
    def run_check(
        self,
        expected="maas",
        details=HEALTHY,
        wait=0,
        status=0,
        datasource="maas",
        datasource_exit=0,
        error=None,
    ):
        responses = [
            subprocess.CompletedProcess([], wait, "status: done", ""),
            subprocess.CompletedProcess([], status, json.dumps(details), ""),
            subprocess.CompletedProcess([], datasource_exit, datasource, ""),
        ]
        output = io.StringIO()
        with patch.dict(
            os.environ, {"BLUEFIELD_EXPECTED_DATASOURCE": expected}
        ):
            with patch.object(
                helper.subprocess, "run", side_effect=error or responses
            ) as query:
                with contextlib.redirect_stdout(output):
                    with contextlib.redirect_stderr(output):
                        outcome = helper.main()
        return outcome, output.getvalue(), query

    def test_healthy_matching_datasource_passes_with_bounded_commands(self):
        outcome, output, query = self.run_check()
        self.assertEqual(outcome, 0)
        self.assertIn("PASS:", output)
        self.assertEqual(
            [call.kwargs["timeout"] for call in query.call_args_list],
            [120, 30, 30],
        )
        self.assertEqual(
            query.call_args_list[0].args[0], ["cloud-init", "status", "--wait"]
        )

    def test_wrong_datasource_fails(self):
        outcome, output, _ = self.run_check(datasource="nocloud")
        self.assertEqual(outcome, 1)
        self.assertIn("datasource differs", output)

    def test_running_disabled_error_or_degraded_status_cannot_pass(self):
        for state in [
            "running",
            "disabled",
            "error",
            "not run",
            "degraded done",
        ]:
            with self.subTest(state=state):
                details = dict(HEALTHY, extended_status=state)
                self.assertEqual(self.run_check(details=details)[0], 1)
                details = dict(HEALTHY, status=state)
                self.assertEqual(self.run_check(details=details)[0], 1)

    def test_fatal_and_recoverable_errors_in_stages_cannot_pass(self):
        for field, errors in [
            ("errors", ["failed"]),
            ("recoverable_errors", {"WARNING": ["deprecated setting"]}),
        ]:
            with self.subTest(field=field):
                details = copy.deepcopy(HEALTHY)
                details["init"] = {field: errors}
                outcome, output, _ = self.run_check(details=details)
                self.assertEqual(outcome, 1)
                self.assertIn("Cloud-init status details:", output)

    def test_nonzero_status_and_wait_exits_cannot_pass(self):
        self.assertEqual(self.run_check(wait=2)[0], 1)
        self.assertEqual(self.run_check(status=2)[0], 1)

    def test_reporting_warnings_require_independent_network_verification(self):
        for ready in (True, False):
            with self.subTest(ready=ready), patch.object(
                helper, "management_ready", return_value=ready
            ) as network:
                outcome, output, _ = self.run_check(
                    details=REPORTING, wait=2, status=2
                )
                self.assertEqual(outcome, 0 if ready else 1)
                network.assert_called_once_with()
                self.assertIn("WARNING:", output)

    def test_mixed_rename_netplan_fatal_or_unknown_issues_remain_failures(
        self,
    ):
        for message in (
            "Failed to rename devices: nic not present",
            "netplan apply failed",
            "unknown warning",
        ):
            details = copy.deepcopy(REPORTING)
            details["init"] = {"recoverable_errors": {"WARNING": [message]}}
            with self.subTest(message=message), patch.object(
                helper, "management_ready"
            ) as network:
                self.assertEqual(
                    self.run_check(details=details, wait=2, status=2)[0], 1
                )
                network.assert_not_called()
        for category in ("ERROR", "CRITICAL"):
            details = dict(REPORTING, recoverable_errors={category: [WARNING]})
            self.assertEqual(self.run_check(details=details, status=2)[0], 1)

    def test_reporting_match_rejects_late_events_wrong_endpoint_or_cause(self):
        for message in (
            WARNING.replace("init-local/check-cache", "modules-final"),
            WARNING.replace("host='10.239.8.11'", "host='other'"),
            WARNING.replace("Network is unreachable", "Connection refused"),
            "Failed posting event: invalid JSON",
        ):
            self.assertFalse(helper.reporting_warning(message, REPORTING))

    def test_reporting_cannot_mask_fatal_errors_or_wrong_datasource(self):
        for details, datasource in (
            (dict(REPORTING, errors=["fatal failure"]), "maas"),
            (REPORTING, "nocloud"),
        ):
            with patch.object(helper, "management_ready") as network:
                self.assertEqual(
                    self.run_check(
                        details=details,
                        datasource=datasource,
                        status=2,
                        wait=2,
                    )[0],
                    1,
                )
                network.assert_not_called()

    def test_reporting_requires_network_expectations(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                self.run_check(details=REPORTING, status=2, wait=2)[0], 2
            )

    def test_invalid_recoverable_shapes_are_errors(self):
        for errors in ([], {"WARNING": "message"}, {"WARNING": [None]}):
            details = dict(HEALTHY, recoverable_errors=errors)
            self.assertEqual(self.run_check(details=details)[0], 2)

    def test_oob_address_and_route_must_match_on_driver_discovered_interface(
        self,
    ):
        address = [
            {
                "ifname": "oob_actual",
                "addr_info": [{"local": "10.241.6.252", "prefixlen": 24}],
            }
        ]
        route = [
            {"dst": "default", "dev": "oob_actual", "gateway": "10.241.6.1"}
        ]
        cases = [
            (address, route, True),
            (address, [], False),
            (address, [dict(route[0], dev="other")], False),
            (address, [dict(route[0], gateway="10.241.6.2")], False),
            ([dict(address[0], addr_info=[])], route, False),
        ]
        for addresses, routes, expected in cases:
            responses = [
                subprocess.CompletedProcess([], 0, json.dumps(value), "")
                for value in (addresses, routes)
            ]
            with self.subTest(addresses=addresses, routes=routes), patch.dict(
                os.environ,
                {
                    "BLUEFIELD_EXPECTED_OOB_ADDRESS": "10.241.6.252/24",
                    "BLUEFIELD_EXPECTED_OOB_GATEWAY": "10.241.6.1",
                },
            ), patch.object(
                helper,
                "discover_interfaces",
                return_value={"oob_actual": {"driver": "mlxbf_gige"}},
            ), patch.object(
                helper, "run_command", side_effect=responses
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(helper.management_ready(), expected)

    def test_missing_or_invalid_expectation_fails_before_commands(self):
        for expected in ["", " ", "MAAS", "maas extra"]:
            with self.subTest(expected=expected):
                outcome, _, query = self.run_check(expected=expected)
                self.assertEqual(outcome, 2)
                query.assert_not_called()

    def test_invalid_status_and_failed_datasource_query_are_errors(self):
        for details in [[], {}, {"status": "done", "errors": "invalid"}]:
            with self.subTest(details=details):
                self.assertEqual(self.run_check(details=details)[0], 2)
        self.assertEqual(self.run_check(datasource_exit=1)[0], 2)

    def test_timeout_and_missing_command_fail_with_diagnostics(self):
        outcome, output, _ = self.run_check(
            error=subprocess.TimeoutExpired(
                "cloud-init", 120, output="still running", stderr="diagnostic"
            )
        )
        self.assertEqual(outcome, 1)
        self.assertIn("timed out", output)
        self.assertIn("still running", output)
        self.assertEqual(
            self.run_check(error=FileNotFoundError("cloud-init"))[0], 2
        )


if __name__ == "__main__":
    unittest.main()
