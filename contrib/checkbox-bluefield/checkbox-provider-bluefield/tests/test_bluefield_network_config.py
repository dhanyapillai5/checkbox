# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only
"""Validate requested configuration against independently supplied observations."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

SCRIPT = (
    Path(__file__).resolve().parents[1] / "bin/bluefield_network_config.py"
)
SPEC = importlib.util.spec_from_file_location(
    "bluefield_network_config", SCRIPT
)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)

CONFIG = {
    "network": {
        "version": 2,
        "ethernets": {
            "management": {
                "match": {"macaddress": "00:11:22:33:44:55"},
                "set-name": "oob",
                "mtu": 1500,
                "addresses": ["192.0.2.10/24"],
                "gateway4": "192.0.2.1",
            },
            "p1": {
                "match": {"macaddress": "00:11:22:33:44:66"},
                "set-name": "p1",
                "mtu": 1500,
            },
        },
    }
}
LINKS = [
    {
        "ifname": "oob",
        "address": "00:11:22:33:44:55",
        "flags": ["UP"],
        "mtu": 1500,
        "addr_info": [{"local": "192.0.2.10", "prefixlen": 24}],
    },
    {
        "ifname": "p1",
        "address": "00:11:22:33:44:66",
        "flags": ["UP"],
        "mtu": 1500,
        "addr_info": [{"local": "fe80::1", "prefixlen": 64}],
    },
]
ROUTES = [{"dst": "default", "gateway": "192.0.2.1", "dev": "oob"}]


class NetworkConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "maas.yaml"
        self.source.write_text(yaml.safe_dump(CONFIG))
        env = patch.dict(
            os.environ, {"BLUEFIELD_MAAS_NETWORK_CONFIG": str(self.source)}
        )
        env.start()
        self.addCleanup(env.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_checks_all_configured_interfaces_without_warning_input(self):
        profiles = helper.load_config()
        self.assertTrue(helper.verify(profiles, LINKS, ROUTES))
        for field, value in (
            ("ifname", "eth2"),
            ("address", "00:00:00:00:00:00"),
            ("flags", []),
            ("mtu", 9000),
            ("addr_info", [{"local": "198.51.100.1", "prefixlen": 24}]),
        ):
            links = copy.deepcopy(LINKS)
            links[1][field] = value
            self.assertFalse(helper.verify(profiles, links, ROUTES), field)
        self.assertFalse(helper.verify(profiles, LINKS[:1], ROUTES))
        self.assertFalse(helper.verify(profiles, LINKS + [LINKS[1]], ROUTES))

    def test_static_prefix_address_readiness_and_required_routes(self):
        profiles = helper.load_config()
        for entry in (
            {"local": "192.0.2.10", "prefixlen": 25},
            {"local": "192.0.2.10", "prefixlen": 24, "tentative": True},
            {"local": "192.0.2.10", "prefixlen": 24, "dadfailed": True},
        ):
            links = copy.deepcopy(LINKS)
            links[0]["addr_info"] = [entry]
            self.assertFalse(helper.verify(profiles, links, ROUTES))
        for routes in (
            [],
            [dict(ROUTES[0], dev="p1")],
            [dict(ROUTES[0], gateway="192.0.2.2")],
            [dict(ROUTES[0], table=100)],
        ):
            self.assertFalse(helper.verify(profiles, LINKS, routes))

    def test_unsupported_topologies_or_dynamic_settings_fail_explicitly(self):
        cases = []
        for change in (
            {"dhcp4": True},
            {"dhcp6": True},
            {"accept-ra": True},
            {"match": {"name": "eth*"}},
            {"mtu": "1500"},
            {"routes": [{"to": "default", "via": "bad"}]},
            {"wakeonlan": True},
        ):
            config = copy.deepcopy(CONFIG)
            config["network"]["ethernets"]["p1"].update(change)
            cases.append(config)
        config = copy.deepcopy(CONFIG)
        config["network"]["bridges"] = {"br0": {"interfaces": ["p1"]}}
        cases.extend(
            [config, {}, {"network": {"version": 2, "ethernets": {}}}]
        )
        for config in cases:
            self.source.write_text(yaml.safe_dump(config))
            with self.assertRaises(ValueError):
                helper.load_config()

    def test_reference_required_without_local_fallback_and_missing_file(self):
        for value in ("", "relative.yaml"):
            with patch.dict(
                os.environ, {"BLUEFIELD_MAAS_NETWORK_CONFIG": value}
            ), patch.object(helper.Path, "read_text") as read:
                with self.assertRaises(ValueError):
                    helper.load_config()
                read.assert_not_called()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                helper.load_config()
        self.source.unlink()
        with self.assertRaises(OSError):
            helper.load_config()

    def test_collection_requires_maas_and_bounded_successful_queries(self):
        values = ["maas", json.dumps(LINKS), json.dumps(ROUTES), "[]"]
        responses = [subprocess.CompletedProcess([], 0, v, "") for v in values]
        with patch.object(
            helper.subprocess, "run", side_effect=responses
        ) as run:
            self.assertIn(
                ("00:11:22:33:44:66", "p1"), helper.verify_deployment_network()
            )
            self.assertTrue(
                all(c.kwargs["timeout"] == 30 for c in run.call_args_list)
            )
        with patch.object(helper, "command", return_value="nocloud"):
            with self.assertRaises(ValueError):
                helper.verify_deployment_network()
        with patch.object(
            helper.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, "", "denied"),
        ):
            with self.assertRaises(ValueError):
                helper.command(["ip"])

    def test_route_metrics_tables_ipv6_and_onlink(self):
        expected = {
            "to": "::/0",
            "via": "2001:db8::1",
            "metric": 10,
            "table": 100,
            "on-link": True,
        }
        route = {
            "dst": "default",
            "gateway": "2001:db8::1",
            "dev": "oob",
            "metric": 10,
            "table": 100,
            "flags": ["onlink"],
        }
        self.assertTrue(helper.route_matches(expected, route, "oob"))
        for change in (
            {"metric": 20},
            {"table": 254},
            {"flags": []},
            {"dst": "2001:db8:1::/64"},
        ):
            self.assertFalse(
                helper.route_matches(expected, dict(route, **change), "oob")
            )


if __name__ == "__main__":
    unittest.main()
