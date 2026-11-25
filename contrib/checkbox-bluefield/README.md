<!-- Copyright 2026 Canonical Ltd. -->
<!-- SPDX-License-Identifier: GPL-3.0-only -->

# BlueField Checkbox provider

Reusable BlueField checks in the `com.canonical.contrib.bluefield` namespace.
The [`bluefield-image-smoke` plan](checkbox-provider-bluefield/units/test-plan-smoke.yaml)
selects the jobs below plus stock platform checks. Callers supply independent
expectations for their device and software configuration; no release profile is
built into the checks.

## Install from source

Requires Python venv support, `checkbox-ng`, `checkbox-support`, and the base and
resource providers. On Ubuntu, install matching venv support first (for example,
`python3.12-venv` for Python 3.12). From the Checkbox repository root:

```bash
python3 -m venv "$HOME/bluefield-checkbox-venv"
```

```bash
. "$HOME/bluefield-checkbox-venv/bin/activate"
```

```bash
python3 -m pip install ./checkbox-ng ./checkbox-support
```

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

```bash
python3 providers/resource/manage.py develop -d "$PROVIDERPATH"
```

```bash
python3 providers/base/manage.py develop -d "$PROVIDERPATH"
```

Keep the venv active and use the same `PROVIDERPATH` when running Checkbox.
Jobs use installed system tools; root jobs require an appropriate privilege
mechanism. The plan needs `fwts`, `xz`, `lsblk`, `lshw`, `systemctl`, `timeout`,
`cloud-init`, `cloud-id`, `ip`, `devlink`, APT/dpkg tools, `ldd`, `ovs-vsctl`, and
the DOCA capability tool. Network parsing requires PyYAML.

## Jobs and inputs

IDs below have the prefix `bluefield/`. Links open executable job definitions.
File inputs must be readable on the tested device; use absolute paths.
See [reference formats and examples](checkbox-provider-bluefield/data/README.md).
Prepare expectations from independent software, hardware and deployment
references, not by copying observed state to construct passing inputs.

| Job | Launcher input | Assertion |
|---|---|---|
| [`kernel/running-release`](checkbox-provider-bluefield/units/kernel/jobs.yaml) | `BLUEFIELD_EXPECTED_KERNEL` | Exact running kernel release |
| [`kernel/boot-arguments`](checkbox-provider-bluefield/units/kernel/boot-args.yaml) | `BLUEFIELD_REQUIRED_BOOT_ARGS`, optional `BLUEFIELD_FORBIDDEN_BOOT_ARGS` | Required/forbidden complete tokens before `--`; extra arguments allowed |
| [`packages/required-inventory`](checkbox-provider-bluefield/units/packages/jobs.yaml) | `BLUEFIELD_CANDIDATE_INVENTORY`, `BLUEFIELD_REQUIRED_PACKAGES` | Required subset fully installed with exact reference versions/architectures |
| [`packages/required-holds`](checkbox-provider-bluefield/units/packages/jobs.yaml) | `BLUEFIELD_REQUIRED_HOLDS` | Required hold subset; extra holds allowed |
| [`packages/expected-conflicts`](checkbox-provider-bluefield/units/packages/jobs.yaml) | `BLUEFIELD_EXPECTED_CONFLICTS` | Exact Conflicts fields of fully installed packages |
| [`modules/required-loaded`](checkbox-provider-bluefield/units/modules/jobs.yaml) | `BLUEFIELD_REQUIRED_MODULES` | Every listed module present in `/proc/modules` |
| [`pci/expected-bindings`](checkbox-provider-bluefield/units/pci/jobs.yaml) | `BLUEFIELD_EXPECTED_PCI` | Required PCI addresses match vendor/device IDs and drivers |
| [`interfaces/expected-roles`](checkbox-provider-bluefield/units/interfaces/jobs.yaml) | `BLUEFIELD_EXPECTED_INTERFACES` | Unique devlink roles mapped to distinct existing netdevs |
| [`management/expected-interfaces`](checkbox-provider-bluefield/units/management/jobs.yaml) | `BLUEFIELD_EXPECTED_MANAGEMENT` | Unique backing-driver/parent-driver matches |
| [`management/tmfifo-address`](checkbox-provider-bluefield/units/management/address.yaml) | `BLUEFIELD_EXPECTED_TMFIFO_ADDRESS` | Exact required address/prefix on discovered DPU tmfifo interface |
| [`management/tmfifo-address-trial`](checkbox-provider-bluefield/units/management/trial.yaml) | `BLUEFIELD_TEST_TMFIFO_ADDRESS` | Temporary IPv4 assignment and UP state; original addresses and state restored |
| [`network/deployment-config`](checkbox-provider-bluefield/units/network/jobs.yaml) | `BLUEFIELD_MAAS_NETWORK_CONFIG` | MAAS-requested interface identity/name, admin state, MTU, static addresses and routes |
| [`cloud-init/completed`](checkbox-provider-bluefield/units/cloud-init/jobs.yaml) | `BLUEFIELD_EXPECTED_DATASOURCE`, `BLUEFIELD_MAAS_NETWORK_CONFIG` | Completed cloud-init, matching datasource and classified diagnostics |
| [`doca/device-query`](checkbox-provider-bluefield/units/doca/jobs.yaml) | `BLUEFIELD_EXPECTED_PCI` | Required device/common capability queries and representative library resolution |
| [`services/required-state`](checkbox-provider-bluefield/units/services/jobs.yaml) | `BLUEFIELD_REQUIRED_SERVICES` | Loaded units, exact active/substates and `Result=success` |
| [`services/enablement`](checkbox-provider-bluefield/units/services/enablement.yaml) | `BLUEFIELD_SERVICE_ENABLEMENT` | Exact enabled/disabled states, including SysV-backed units |
| [`image/absent-files`](checkbox-provider-bluefield/units/image/jobs.yaml) | `BLUEFIELD_ABSENT_FILES` | All specified paths absent, including dangling symlinks |
| [`image/release-marker`](checkbox-provider-bluefield/units/image/jobs.yaml) | `BLUEFIELD_EXPECTED_RELEASE_SUFFIX` | One release identifier in `/etc/mlnx-release` ending in the supplied suffix |
| [`image/config-settings`](checkbox-provider-bluefield/units/image/settings.yaml) | `BLUEFIELD_EXPECTED_SETTINGS` | Unique literal assignments match file/key/value expectations |
| [`ovs/initialization`](checkbox-provider-bluefield/units/ovs/init.yaml) | `BLUEFIELD_OVS_INIT_POLICY` | Expected global settings, temporary bridge/internal-port initialization and verified cleanup |
| [`logs/kernel-journal.txt`](checkbox-provider-bluefield/units/logs/attachments.yaml) | None | Current-boot kernel journal attachment |
| [`logs/service-journal.txt`](checkbox-provider-bluefield/units/logs/attachments.yaml) | `BLUEFIELD_REQUIRED_SERVICES` | Current-boot journals for the required services |

Stock jobs use `com.canonical.certification::`:

| Selected job | Purpose |
|---|---|
| [`disk/detect`](../../providers/base/units/disk/jobs.pxu) | Disk discovery; not filesystem health or identity validation |
| [`memory/info`](../../providers/base/units/memory/jobs.pxu) | Visible versus installed memory using stock tolerance |
| [`services/no-failed-units`](../../providers/base/units/services/jobs.yaml) | Failed-unit detection; no reboot or required-unit policy |
| [`miscellanea/oops`, `miscellanea/oops_results.log`](../../providers/base/units/miscellanea/jobs.pxu) | FWTS oops check and compressed results attachment |

## Input formats

| Input | Format / example |
|---|---|
| `BLUEFIELD_EXPECTED_KERNEL` | Exact release string |
| `BLUEFIELD_REQUIRED_BOOT_ARGS`, `BLUEFIELD_FORBIDDEN_BOOT_ARGS` | Unique whitespace-free tokens; lists must be disjoint; required list nonempty |
| `BLUEFIELD_CANDIDATE_INVENTORY` | Headerless package/version/architecture TSV; [example](checkbox-provider-bluefield/data/packages/package-inventory.tsv) |
| `BLUEFIELD_REQUIRED_PACKAGES`, `BLUEFIELD_REQUIRED_HOLDS` | Nonempty whitespace-separated unique, unqualified package names |
| `BLUEFIELD_EXPECTED_CONFLICTS` | Headerless package/exact Conflicts TSV; [example](checkbox-provider-bluefield/data/packages/expected-conflicts.tsv) |
| `BLUEFIELD_REQUIRED_MODULES` | Whitespace-separated module names as listed in `/proc/modules`, with underscores |
| `BLUEFIELD_EXPECTED_PCI` | Headerless PCI-address/vendor/device/driver TSV; [example](checkbox-provider-bluefield/data/pci/expected-pci.tsv) |
| `BLUEFIELD_EXPECTED_INTERFACES` | JSON role list: physical `port`; pcipf `controller`/`pfnum`/`external`; pcisf `controller`/`pfnum`/`sfnum`; [example](checkbox-provider-bluefield/data/interfaces/expected-interfaces.json) |
| `BLUEFIELD_EXPECTED_MANAGEMENT` | JSON role objects with `driver` and optional `parent_driver`; [example](checkbox-provider-bluefield/data/management/expected-management.json) |
| `BLUEFIELD_EXPECTED_TMFIFO_ADDRESS` | Required IP address/prefix; no default address |
| `BLUEFIELD_TEST_TMFIFO_ADDRESS` | Explicit temporary unicast IPv4/prefix, such as `192.168.100.2/30`; no built-in default |
| `BLUEFIELD_MAAS_NETWORK_CONFIG` | Independent MAAS-generated Netplan; [example](checkbox-provider-bluefield/data/network/maas-network-reference.yaml) |
| `BLUEFIELD_EXPECTED_DATASOURCE` | Expected `cloud-id` result, such as `maas` |
| `BLUEFIELD_REQUIRED_SERVICES` | Whitespace-separated `unit.service:active:running` or `unit.service:active:exited` |
| `BLUEFIELD_SERVICE_ENABLEMENT` | Unique `unit.service:enabled\|disabled` or `unit.timer:enabled\|disabled` tokens |
| `BLUEFIELD_ABSENT_FILES` | Nonempty whitespace-separated unique normalized absolute paths |
| `BLUEFIELD_EXPECTED_RELEASE_SUFFIX` | Nonempty whitespace-free suffix starting `_` |
| `BLUEFIELD_EXPECTED_SETTINGS` | JSON list of string `file`/`key`/`value` objects; [example](checkbox-provider-bluefield/data/image/expected-settings.json) |
| `BLUEFIELD_OVS_INIT_POLICY` | JSON string map `other_config` and explicit `datapath_type`; [example](checkbox-provider-bluefield/data/ovs/init-policy.json) |

### Behaviour and limits

- Journal attachments include the boot ID and complete available current-boot
  records, without severity filtering or message classification. Collection has
  a 60-second timeout; errors fail the attachment job. Empty service journals
  are not health assertions. Attachments are included in Checkbox submission
  data/report archives; HTML and JUnit present outcomes, not necessarily full log
  contents. Retain the exported submission archive to preserve diagnostic data.

- The plan selects the temporary tmfifo trial, not the read-only configured-IP
  check. It discovers tmfifo by driver identity, adds only a missing test address
  with `noprefixroute`, brings the link UP if needed, and restores original
  addresses/admin state in cleanup. A DOWN interface with existing addresses or
  the test IP under a conflicting prefix is rejected before modification.
  Cleanup failures fail the job. SIGTERM is handled; SIGKILL cannot run cleanup.
  Avoid concurrent interface configuration. No persistent configuration, OOB
  interface or host-side connectivity is changed/tested.

- Network checks support direct MAC-matched static Ethernet with networkd.
  DHCP, explicit RA, bridges, bonds, VLANs and unsupported settings fail.
  Additional routes, interfaces and IPv6 link-local addresses are allowed.
  DNS behaviour and connectivity are not checked. There is no fallback to
  installed Netplan for expectations.
- Cloud-init waits up to 120 seconds. Fatal/stage errors and unclassified issues
  fail. Only narrowly classified early MAAS reporting and missing-interface
  rename warnings can be retained after direct final-network verification;
  warnings remain in output. See the [classifier](checkbox-provider-bluefield/bin/bluefield_cloud_init.py).
- DOCA uses `/opt/mellanox/doca/tools/doca_caps`: device enumeration, per-device
  common capability JSON and `ldd` resolution of common/argp libraries. Optional
  unsupported capabilities are allowed. No traffic or acceleration test runs.
- Literal settings accept quotes, optional `export` and trailing comments.
  Duplicate assignments, shell expansion, substitutions, semicolons and
  continuations fail. Files are read, never sourced. Matching file contents does
  not establish that a service consumed them.
- Boot checks compare token presence, not precedence of conflicting values.
  Quoted argument values containing whitespace are unsupported. Module checks
  assert loaded modules, not built-in drivers. Release checks assert a suffix,
  not the complete bundle version.
- OVS checks do not change globals or restart services. They create an owned
  temporary bridge/internal port, require a valid datapath ID and positive
  ofports without errors, then delete them and compare selected pre/post
  configuration. Cleanup is attempted on failure and interruption, including
  SIGTERM; SIGKILL cannot run cleanup. Ownership changes, unexpected attached
  ports and cleanup failures fail. Avoid concurrent OVS configuration changes.
  Physical ports, bonds, representors, forwarding and hardware offload are not
  exercised by this job.

## Running the smoke plan

Use the [complete launcher template](examples/smoke.launcher) with the
[example instructions](examples/README.md) for all selected jobs.

Create a launcher using the input names above. For example, this selects only
the kernel job; omit `match` to select the entire plan and supply every selected
job's required inputs.

```ini
[launcher]
launcher_version = 1
app_id = com.canonical.contrib.bluefield:smoke
app_version = 0.1.0
stock_reports = text, submission_files
session_title = BlueField checks

[test plan]
unit = com.canonical.contrib.bluefield::bluefield-image-smoke
forced = yes

[test selection]
forced = yes
match = .*bluefield/kernel/running-release$

[ui]
type = silent

[environment]
BLUEFIELD_EXPECTED_KERNEL = REPLACE_WITH_EXPECTED_RELEASE
```

```bash
checkbox-cli launcher ./bluefield-smoke.launcher
```

Inspect individual job outcomes and unexpected skips; CLI completion alone does
not establish a pass. Retain the launcher, input files, source revisions and
reports. Example references describe formats, not approved device profiles.

## Development checks

With the venv active and `P` set as above:

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

The managed suite uses ShellCheck for inline shell commands and Flake8 for
scripts. For device trials, exercise mismatched/missing expectations by changing
copied inputs, preserving live drivers, packages and management configuration.

Provider authoring: [Checkbox documentation](https://checkbox.readthedocs.io/en/latest/).
