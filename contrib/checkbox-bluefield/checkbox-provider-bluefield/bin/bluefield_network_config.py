#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Compare MAAS-generated static Ethernet Netplan intent with live state."""

import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml


def command(args):
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=30,
        env=dict(os.environ, LC_ALL="C"),
    )
    print("Command: {}; exit: {}".format(" ".join(args), result.returncode))
    print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode:
        raise ValueError("Unable to collect network evidence")
    return result.stdout


def load_config():
    """Read the caller-supplied independent MAAS reference."""
    value = os.environ.get("BLUEFIELD_MAAS_NETWORK_CONFIG", "")
    if not value or not Path(value).is_absolute():
        raise ValueError(
            "Supply BLUEFIELD_MAAS_NETWORK_CONFIG absolute MAAS reference path"
        )
    source = Path(value)
    print("Deployment network configuration: " + str(source))
    data = yaml.safe_load(source.read_text())
    network = data.get("network") if isinstance(data, dict) else None
    if not isinstance(network, dict) or network.get("version") != 2:
        raise ValueError("Require MAAS Netplan network version 2")
    if set(network) - {"version", "renderer", "ethernets"}:
        raise ValueError(
            "Only directly addressed Ethernet configurations supported"
        )
    if network.get("renderer", "networkd") != "networkd":
        raise ValueError("Only networkd configurations supported")
    ethernets = network.get("ethernets")
    if not isinstance(ethernets, dict) or not ethernets:
        raise ValueError("Require nonempty Ethernet deployment configuration")
    profiles = []
    for key, config in ethernets.items():
        if not isinstance(config, dict):
            raise ValueError("Invalid Ethernet configuration")
        supported = {
            "match",
            "set-name",
            "mtu",
            "addresses",
            "gateway4",
            "gateway6",
            "routes",
            "dhcp4",
            "dhcp6",
            "accept-ra",
            "optional",
            "link-local",
            "nameservers",
            "renderer",
        }
        if set(config) - supported:
            raise ValueError("Unsupported Ethernet settings on " + str(key))
        if any(
            config.get(k, False) is not False
            for k in (
                "dhcp4",
                "dhcp6",
                "accept-ra",
            )
        ):
            raise ValueError("DHCP/RA verification is not implemented")
        if config.get("renderer", "networkd") != "networkd":
            raise ValueError("Only networkd configurations supported")
        if config.get("link-local", ["ipv6"]) not in ([], ["ipv6"]):
            raise ValueError(
                "Only optional IPv6 link-local addressing supported"
            )
        match = config.get("match", {})
        mac = match.get("macaddress") if isinstance(match, dict) else None
        name = config.get("set-name", key)
        if (
            not isinstance(mac, str)
            or not re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}", mac)
            or set(match) != {"macaddress"}
            or not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name)
        ):
            raise ValueError("Require exact MAC match and valid final name")
        mtu = config.get("mtu")
        if mtu is not None and (type(mtu) is not int or mtu < 68):
            raise ValueError("Invalid configured MTU")
        addresses = config.get("addresses", [])
        if not isinstance(addresses, list):
            raise ValueError("Require static address/prefix list")
        for value in addresses:
            if not isinstance(value, str) or "/" not in value:
                raise ValueError("Require static address/prefix strings")
            ipaddress.ip_interface(value)
        routes = config.get("routes", [])
        if not isinstance(routes, list):
            raise ValueError("Invalid configured routes")
        routes = list(routes)
        for family in (4, 6):
            gateway = config.get("gateway" + str(family))
            if gateway is not None:
                if ipaddress.ip_address(gateway).version != family:
                    raise ValueError("Gateway address family mismatch")
                routes.append({"to": "default", "via": gateway})
        for route in routes:
            if (
                not isinstance(route, dict)
                or set(route) - {"to", "via", "metric", "table", "on-link"}
                or not {"to", "via"} <= set(route)
            ):
                raise ValueError("Unsupported static route")
            gateway = ipaddress.ip_address(route["via"])
            if route["to"] != "default":
                target = ipaddress.ip_network(route["to"], strict=False)
                if target.version != gateway.version:
                    raise ValueError("Route address family mismatch")
            for field in ("metric", "table"):
                if field in route and (
                    type(route[field]) is not int or route[field] < 0
                ):
                    raise ValueError("Invalid route " + field)
            if "on-link" in route and type(route["on-link"]) is not bool:
                raise ValueError("Invalid route on-link setting")
        profiles.append(
            {
                "name": name,
                "mac": mac.lower(),
                "mtu": mtu,
                "addresses": addresses,
                "routes": routes,
            }
        )
    if any(
        len({p[k] for p in profiles}) != len(profiles) for k in ("name", "mac")
    ):
        raise ValueError("Ambiguous configured interface identities")
    print("Expected network subset: " + json.dumps(profiles, sort_keys=True))
    return profiles


def route_matches(expected, observed, name):
    gateway = ipaddress.ip_address(expected["via"])
    target = expected["to"]
    if target == "default":
        target = "0.0.0.0/0" if gateway.version == 4 else "::/0"
    target = ipaddress.ip_network(target, strict=False)
    destination = observed.get("dst")
    if destination == "default":
        destination = "0.0.0.0/0" if gateway.version == 4 else "::/0"
    if not destination:
        return False
    table = observed.get("table", "main")
    table = 254 if table == "main" else table
    return (
        observed.get("dev") == name
        and observed.get("gateway") == str(gateway)
        and ipaddress.ip_network(destination, strict=False) == target
        and table == expected.get("table", 254)
        and observed.get("type", "unicast") == "unicast"
        and (
            "metric" not in expected
            or observed.get("metric", 0) == expected["metric"]
        )
        and (
            "on-link" not in expected
            or ("onlink" in observed.get("flags", [])) == expected["on-link"]
        )
    )


def verify(profiles, links, routes):
    """Verify every configured interface, irrespective of recorded warnings."""
    if not isinstance(links, list) or not isinstance(routes, list):
        raise ValueError("Invalid network observation JSON")
    passed = True
    for profile in profiles:
        name = profile["name"]
        matched = [
            p for p in links if p.get("address", "").lower() == profile["mac"]
        ]
        named = [p for p in links if p.get("ifname") == name]
        if len(matched) != 1 or len(named) != 1 or matched[0] != named[0]:
            print("FAIL: requested interface name/MAC not enforced: " + name)
            passed = False
            continue
        link = named[0]
        addresses = set()
        usable = True
        for entry in link.get("addr_info", []):
            value = ipaddress.ip_interface(
                "{}/{}".format(entry["local"], entry["prefixlen"])
            )
            if value.version == 6 and value.ip.is_link_local:
                continue
            usable &= not (entry.get("tentative") or entry.get("dadfailed"))
            addresses.add(value)
        expected = {ipaddress.ip_interface(v) for v in profile["addresses"]}
        interface_ok = (
            "UP" in link.get("flags", [])
            and (profile["mtu"] is None or link.get("mtu") == profile["mtu"])
            and usable
            and addresses == expected
            and all(
                any(route_matches(r, o, name) for o in routes)
                for r in profile["routes"]
            )
        )
        print(
            ("Verified: " if interface_ok else "FAIL: ")
            + name
            + " requested name/MAC, admin UP, configured MTU, addresses/routes"
        )
        passed &= bool(interface_ok)
    return bool(passed)


def verify_deployment_network():
    """Return intended identities after successful evidence verification."""
    if command(["cloud-id"]).strip() != "maas":
        raise ValueError("Network deployment check requires MAAS datasource")
    profiles = load_config()
    links = json.loads(command(["ip", "-j", "address", "show"]))
    routes = []
    for family in ("-4", "-6"):
        observed = json.loads(
            command(["ip", "-j", family, "route", "show", "table", "all"])
        )
        if not isinstance(observed, list):
            raise ValueError("Invalid route observation JSON")
        routes.extend(observed)
    if not verify(profiles, links, routes):
        raise ValueError("MAAS-generated network configuration not enforced")
    return {(p["mac"], p["name"]) for p in profiles}


def main():
    try:
        verify_deployment_network()
        print("PASS: requested static Ethernet configuration is enforced")
        print(
            "Scope: DNS, users, SSH keys and connectivity are separate checks"
        )
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        yaml.YAMLError,
        subprocess.TimeoutExpired,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
