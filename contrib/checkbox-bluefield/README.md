<!-- Copyright 2026 Canonical Ltd. -->
<!-- SPDX-License-Identifier: GPL-3.0-only -->

# BlueField Checkbox provider

Provider scaffold for reusable BlueField image validation and linux-bluefield
kernel regression jobs in the `com.canonical.contrib.bluefield` namespace.

Planned test plans are `bluefield-image-smoke`, `bluefield-image-full-release`
and `bluefield-kernel-regression`. Jobs and plan selections are delivered in
separate changes after the scaffold. Provider registration and validation alone
do not establish hardware coverage.

## Requirements and source installation

Provider management requires `checkbox-ng`. The scaffold does not depend on
stock providers or `checkbox-support`. Use a dedicated Python virtual
environment. On Ubuntu, install matching venv support first: importing `venv`
alone does not establish that `ensurepip` is available. Ubuntu 24.04 with the
default Python 3.12 needs `python3.12-venv`.

Start in the copied or checked-out Checkbox repository root:

```bash
python3 -m venv "$HOME/bluefield-checkbox-venv"
```

```bash
. "$HOME/bluefield-checkbox-venv/bin/activate"
```

```bash
python3 -m pip install ./checkbox-ng
```

Register the provider:

```bash
P="$PWD/contrib/checkbox-bluefield/checkbox-provider-bluefield"
```

```bash
export PROVIDERPATH="$HOME/.local/share/bluefield-checkbox/providers"
```

```bash
mkdir -p "$PROVIDERPATH"
```

```bash
python3 "$P/manage.py" develop -d "$PROVIDERPATH"
```

Keep the same environment and `PROVIDERPATH` when invoking Checkbox. Do not mix
this registration with a separate snap runtime. Record the runtime and provider
source revision, including any uncommitted changes, with each run. Provider
version `0.1.0` alone does not identify source changes. ARM64 BF3 installation
and execution still need verification.

## Local development checks

With the environment active and `P` set as above:

```bash
python3 -m pip install black flake8
```

```bash
python3 "$P/manage.py" validate
```

```bash
python3 "$P/manage.py" test
```

```bash
black --check --line-length 79 "$P"
```

```bash
flake8 "$P"
```

`manage.py test` uses ShellCheck when checking inline shell job commands.
Install the distribution's `shellcheck` package when adding those jobs.
Deployment, network recovery, dependency delivery and cleanup belong to the
surrounding workflow. Setup must preserve the image's kernel, DOCA and drivers.
