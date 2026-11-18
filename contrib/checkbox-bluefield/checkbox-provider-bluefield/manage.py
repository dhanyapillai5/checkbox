#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# SPDX-License-Identifier: GPL-3.0-only

from plainbox.provider_manager import N_, setup

setup(
    name="checkbox-provider-bluefield",
    namespace="com.canonical.contrib.bluefield",
    version="0.1.0",
    description=N_("Reusable BlueField platform validation jobs"),
    gettext_domain="checkbox-provider-bluefield",
)
