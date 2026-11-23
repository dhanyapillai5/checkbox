<!-- Copyright 2026 Canonical Ltd. -->
<!-- SPDX-License-Identifier: GPL-3.0-only -->

# BlueField Checkbox provider

Reusable BlueField image validation and linux-bluefield
kernel regression jobs in the `com.canonical.contrib.bluefield` namespace.

The `bluefield-image-smoke` plan currently checks the running kernel release,
required installed packages, required loaded kernel modules and expected DPU
PCI identities/driver bindings, interface/representor identities and DPU
management-interface presence and tmfifo address assignment.
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

The job `bluefield/cloud-init/completed` waits up to 120 seconds for cloud-init,
then collects JSON status and `cloud-id` (each with a 30-second timeout). Supply
`BLUEFIELD_EXPECTED_DATASOURCE` as the expected `cloud-id` value from deployment
configuration, for example `maas` for the customized MAAS image. Do not assume
that value for stock BFBs. Status details and command diagnostics are captured.

Require `done` status, the expected datasource and no fatal/stage errors.
Timeouts, disabled/incomplete states, invalid status and unknown recoverable
issues fail. Exit code 2 or `degraded done` alone is not sufficient to classify
the outcome. The only accepted recoverable messages are early MAAS cache/search
event-posting warnings caused by network-unreachable errors to the datasource's
MAAS status endpoint. These are retained as `WARNING:` diagnostics, not hidden.
Acceptance additionally requires `BLUEFIELD_EXPECTED_OOB_ADDRESS` (address/prefix)
and `BLUEFIELD_EXPECTED_OOB_GATEWAY`, supplied from deployment configuration.
The job discovers the unique `mlxbf_gige` interface and verifies that address
and default route using read-only, bounded `ip` queries. No lab defaults apply.
Rename failures, Netplan failures, unrecognised warnings and recoverable
ERROR/CRITICAL entries remain blocking. No blanket deprecation exception exists.
The job can pass with reporting warnings; it does not claim clean completion.
Resulting user, SSH-key and network state require separate assertions.
Cloud-init-check BF3 execution remains unverified.

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

The job `bluefield/modules/required-loaded` reads `/proc/modules` and checks every
name in the whitespace-separated `BLUEFIELD_REQUIRED_MODULES` input. The DPU
smoke list includes `mlx5_core`, `mlx5_ib`, `openvswitch`, `mlxbf_gige`,
`mlxbf_tmfifo`, `ib_core` and `ib_uverbs`. Use module names as listed in
`/proc/modules`, with underscores. Missing/invalid input, unreadable module state
and missing modules fail the check. It does not load modules or require root.
Built-in drivers are not listed in `/proc/modules`; this job specifically asserts
loaded modules. Device binding, driver/package consistency and RDMA functionality
require separate assertions. Module-check BF3 execution remains unverified.

The job `bluefield/pci/expected-bindings` takes `BLUEFIELD_EXPECTED_PCI`, an
absolute path to a headerless TSV file on the DPU. Each row contains the full
PCI address (domain:bus:slot.function), four-digit lowercase vendor ID, four-digit
lowercase device ID and bound driver name. Separate fields with tabs; omit `0x`
prefixes. Supply expectations from the agreed DPU hardware/topology configuration,
not by copying the observed state for qualification. PCI addresses are specific
to that configuration and may differ between systems.

The check reads `/sys/bus/pci/devices` without changing driver bindings. Every
listed address must have the expected identity and driver; extra devices are
allowed. Missing/unbound devices, identity/driver mismatches, invalid inputs and
read errors fail the job. Host PCI enumeration, RDMA functionality, interface
roles and driver/package consistency require separate checks. PCI-check BF3
execution remains unverified.

The job `bluefield/interfaces/expected-roles` takes
`BLUEFIELD_EXPECTED_INTERFACES`, an absolute path to a JSON list of expected
devlink identities. It matches Ethernet ports by role, records each discovered
interface name and verifies the interface exists in `/sys/class/net`. Names and
devlink port handles are not matching criteria. Each role must match exactly one
port and a distinct interface; extra ports are allowed. Required fields are:

- `physical`: `port`.
- `pcipf`: `controller`, `pfnum`, `external` (boolean).
- `pcisf`: `controller`, `pfnum`, `sfnum`.

For example, a two-port topology with host-PF and SF representors uses:

```json
[
  {"flavour": "physical", "port": 0},
  {"flavour": "physical", "port": 1},
  {"flavour": "pcipf", "controller": 1, "pfnum": 0, "external": true},
  {"flavour": "pcipf", "controller": 1, "pfnum": 1, "external": true},
  {"flavour": "pcisf", "controller": 0, "pfnum": 0, "sfnum": 0},
  {"flavour": "pcisf", "controller": 0, "pfnum": 1, "sfnum": 0}
]
```

Supply identities from the agreed deployment topology; do not generate passing
expectations from observed state for qualification. The check runs read-only
`devlink -j port show` with a 30-second timeout. Missing/ambiguous roles, absent
netdevs, invalid inputs and query/read failures fail. It does not assert link
state, speed, traffic, SF function health or OVS membership. Interface-check BF3
execution remains unverified.

The job `bluefield/management/expected-interfaces` discovers DPU management
interfaces through sysfs backing-driver identities, reporting their actual names.
`BLUEFIELD_EXPECTED_MANAGEMENT` points to a JSON object of named roles. Each role
specifies `driver` and optionally `parent_driver` (the immediate parent device's
driver). For BlueField OOB and DPU-side tmfifo, use:

```json
{
  "oob": {"driver": "mlxbf_gige"},
  "tmfifo": {"driver": "virtio_net", "parent_driver": "bf-tmfifo"}
}
```

The parent identity distinguishes tmfifo from unrelated virtio interfaces.
Names and numbered platform-device paths are not matching criteria. Require
exactly one distinct interface per role; extra interfaces are allowed. Missing
or ambiguous matches, invalid inputs and read errors fail. The check is
read-only and needs no host RShim access. It does not assert IP addresses,
routes, link state, connectivity or host/BMC ownership. Management-check BF3
execution remains unverified.

The job `bluefield/management/tmfifo-address` discovers the DPU tmfifo interface
through `virtio_net` under `bf-tmfifo`, then uses read-only `ip -j address show`
with a 30-second timeout. Set `BLUEFIELD_EXPECTED_TMFIFO_ADDRESS` to the exact
address/prefix required by the image's network configuration. For the stock-BFB
sandbird trial, Netplan explicitly configures `192.168.100.2/30`; confirm the
customized candidate's configuration before qualification. The expected address
is supplied independently of the observed running address.

The check records the discovered name and assigned addresses. Extra addresses
are allowed; missing/ambiguous tmfifo interfaces, missing expected addresses,
invalid inputs and query/read errors fail. Both address and prefix must match.
This assertion does not require an OOB IP, routes, DNS, host connectivity or host
RShim ownership. Tmfifo-address BF3 execution remains unverified.

Create `bluefield-smoke.launcher`, replacing the candidate input placeholders:

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
BLUEFIELD_EXPECTED_DATASOURCE = REPLACE_WITH_DEPLOYMENT_DATASOURCE
BLUEFIELD_EXPECTED_OOB_ADDRESS = REPLACE_WITH_DEPLOYMENT_OOB_ADDRESS_PREFIX
BLUEFIELD_EXPECTED_OOB_GATEWAY = REPLACE_WITH_DEPLOYMENT_OOB_GATEWAY
BLUEFIELD_EXPECTED_KERNEL = REPLACE_WITH_CANDIDATE_KERNEL_RELEASE
BLUEFIELD_CANDIDATE_INVENTORY = /REPLACE_WITH_CANDIDATE_PATH/package-inventory.tsv
BLUEFIELD_REQUIRED_PACKAGES = REPLACE_WITH_REQUIRED_PACKAGE_NAMES
BLUEFIELD_REQUIRED_MODULES = mlx5_core mlx5_ib openvswitch mlxbf_gige mlxbf_tmfifo ib_core ib_uverbs
BLUEFIELD_EXPECTED_PCI = /REPLACE_WITH_DPU_CONFIG_PATH/expected-pci.tsv
BLUEFIELD_EXPECTED_INTERFACES = /REPLACE_WITH_DPU_CONFIG_PATH/expected-interfaces.json
BLUEFIELD_EXPECTED_MANAGEMENT = /REPLACE_WITH_DPU_CONFIG_PATH/expected-management.json
BLUEFIELD_EXPECTED_TMFIFO_ADDRESS = REPLACE_WITH_CONFIGURED_TMFIFO_ADDRESS_PREFIX
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
For the module job, verify the required modules pass, an added nonexistent
required name fails, and an empty required list fails. Change only expectations;
do not unload drivers to exercise failure paths. Restore the required list and
finish with a matching run.
For the PCI job, verify matching expectations pass, a deliberately wrong expected
device ID or driver fails, and a missing input fails. Restore matching inputs;
do not unbind devices to exercise failure paths.
For the interface job, verify the six expected roles pass and capture the actual
names. Change an expected SF number to a nonexistent value and verify failure;
verify missing input fails, then restore matching expectations. Do not remove
interfaces to exercise failure paths.
For the management job, verify both roles pass and capture their discovered
names. Change the expected tmfifo parent driver to a nonexistent value and
verify failure. Verify missing input fails, then restore matching expectations.
Change only input files; do not disable management drivers or interfaces.
For the cloud-init job, inspect `cloud-init status --long --format=json` and
`cloud-id` first. Verify healthy matching input passes, a wrong expected
datasource fails, and empty input fails. Restore the correct expectation.
Do not rerun cloud-init or change its state to exercise failure paths.
For the tmfifo address job, verify the configured address/prefix passes, a wrong
address or prefix fails, and missing input fails. Restore the correct expectation
and finish with a matching run; do not change the actual interface configuration.
Deployment, network recovery, dependency delivery and cleanup belong to the
surrounding workflow. Setup must preserve the image's kernel, DOCA and drivers.
