<!-- Copyright 2026 Canonical Ltd. -->
<!-- SPDX-License-Identifier: GPL-3.0-only -->

# BlueField Checkbox provider

Reusable BlueField image validation and linux-bluefield
kernel regression jobs in the `com.canonical.contrib.bluefield` namespace.

The `bluefield-image-smoke` plan currently checks the running kernel release
and required installed packages against candidate expectations.
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

The job `bluefield/packages/required-inventory` takes:

- `BLUEFIELD_CANDIDATE_INVENTORY`: an absolute path to the candidate build's
  `package-inventory.tsv`, copied to the DPU. Each headerless row contains package
  name, exact Debian version and architecture, separated by tabs.
- `BLUEFIELD_REQUIRED_PACKAGES`: whitespace-separated package names. Each must
  appear exactly once in the candidate inventory. The caller supplies the
  reviewed required subset for the candidate, independently of the DPU state.

Each required package must be fully installed with the exact candidate version
and architecture. Extra packages and changes to unselected packages are allowed.
Missing/unreadable inputs, invalid inventories and query failures fail the job.
The check uses read-only `dpkg-query`; it does not install or change packages.

For customized MAAS images, the required subset includes `linux-bluefield`,
`linux-image-<candidate-release>`, `mlxbf-bootimages-signed`, `doca-runtime`,
`doca-devel`, `mlnx-ofed-kernel-modules`, `doca-openvswitch-common` and
`doca-openvswitch-switch`, plus packages listed in the candidate release's
`modified_packages` (currently including `python3-doca-openvswitch`). Resolve
the kernel package name from candidate configuration, not `uname`. Stock BFBs
may have different package names and need their own independent expectations.

Create `bluefield-smoke.launcher`, replacing all three input placeholders:

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
BLUEFIELD_CANDIDATE_INVENTORY = /REPLACE_WITH_CANDIDATE_PATH/package-inventory.tsv
BLUEFIELD_REQUIRED_PACKAGES = REPLACE_WITH_REQUIRED_PACKAGE_NAMES
```

```bash
checkbox-cli launcher ./bluefield-smoke.launcher
```

Inspect job outcomes in the reports; CLI completion alone does not establish a
pass. Record source revisions, candidate inventory checksum and required-package
selection with the reports. These checks do not qualify the complete image or
establish boot integrity or dependency consistency. Package-check BF3 execution
remains unverified.

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
For the package job, verify a match, deliberately changed candidate version,
missing required package and missing input through Checkbox on BF3.
Deployment, network recovery, dependency delivery and cleanup belong to the
surrounding workflow. Setup must preserve the image's kernel, DOCA and drivers.
