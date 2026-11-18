<!-- Copyright 2026 Canonical Ltd. -->
<!-- SPDX-License-Identifier: GPL-3.0-only -->

# BlueField Checkbox provider

Reusable BlueField image validation and linux-bluefield
kernel regression jobs in the `com.canonical.contrib.bluefield` namespace.

The `bluefield-image-smoke` plan currently checks the running kernel release.
Full-release and kernel-regression plans will reuse applicable jobs.

For provider authoring, see the
[Checkbox documentation](https://checkbox.readthedocs.io/en/latest/).

## Requirements and source installation

Provider management requires `checkbox-ng`. This provider does not depend on
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

Keep the same environment and `PROVIDERPATH` when invoking Checkbox.

## Running the smoke plan

The job `bluefield/kernel/running-release` compares the running kernel with
`BLUEFIELD_EXPECTED_KERNEL`. Supply the exact expected release from the image or
kernel candidate, not from the running system. Missing or invalid input and
mismatches fail the job.

Create `bluefield-smoke.launcher`, replacing the expected-kernel placeholder:

```ini
[launcher]
launcher_version = 1
app_id = com.canonical.contrib.bluefield:image-smoke
app_version = 0.1.0
stock_reports = text, submission_files
session_title = BlueField image smoke

[test plan]
unit = com.canonical.contrib.bluefield::bluefield-image-smoke
forced = yes

[test selection]
forced = yes

[ui]
type = silent

[environment]
BLUEFIELD_EXPECTED_KERNEL = REPLACE_WITH_CANDIDATE_KERNEL_RELEASE
```

```bash
checkbox-cli launcher ./bluefield-smoke.launcher
```

Inspect job outcomes in the reports; CLI completion alone does not establish a
pass. Record source revisions and expected inputs with the reports. This single
check does not qualify the complete image. BF3 execution remains unverified.

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
Install the distribution's `shellcheck` package for that check. On BF3, verify
correct, deliberately wrong and missing expected-kernel inputs through Checkbox.
Deployment, network recovery, dependency delivery and cleanup belong to the
surrounding workflow. Setup must preserve the image's kernel, DOCA and drivers.
