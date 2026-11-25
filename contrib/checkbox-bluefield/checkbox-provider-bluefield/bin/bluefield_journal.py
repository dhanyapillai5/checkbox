#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

"""Stream current-boot journal evidence to a Checkbox attachment."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import uuid

from bluefield_services import read_expectations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scope", choices=("kernel", "services"))
    args = parser.parse_args(argv)
    try:
        units = (
            read_expectations(
                os.environ.get("BLUEFIELD_REQUIRED_SERVICES", "")
            )
            if args.scope == "services"
            else {}
        )
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if not boot:
            raise ValueError("Missing current boot identity")
        # journalctl boot descriptors require the compact systemd ID form.
        boot = uuid.UUID(boot).hex
        command = [
            "journalctl",
            "--boot=" + boot,
            "--no-pager",
            "--all",
            "--output=short-iso-precise",
        ]
        if args.scope == "kernel":
            command.append("--dmesg")
        else:
            for unit in units:
                command.extend(["--unit", unit])
        print("Boot ID: " + boot)
        print("Command: " + " ".join(command), flush=True)
        # Inherit stdout so journals stream to the attachment, not RAM. Keep
        # stderr stays separate from journal records.
        result = subprocess.run(
            command,
            timeout=60,
            env=dict(os.environ, LC_ALL="C"),
        )
        if result.returncode:
            raise ValueError(
                "Journal collection failed: exit {}".format(result.returncode)
            )
        return 0
    except (
        OSError,
        UnicodeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
