# Reference input examples

These files document the input formats for the BlueField checks. They are
examples, not approved qualification profiles or a passing deployment bundle.
Supply absolute paths through the launcher; these jobs do not resolve paths
relative to `PLAINBOX_PROVIDER_DATA`.

| File | Purpose and real-run source |
|---|---|
| `packages/package-inventory.tsv` | Synthetic package/version/architecture row. Use the actual candidate build's inventory, not a DPU package export. |
| `packages/expected-conflicts.tsv` | Synthetic package/exact Conflicts TSV. Derive fields from the candidate's pinned customization/release policy, not installed DPU metadata. |
| `image/expected-settings.json` | Synthetic file/key/value expectations. Use literal settings from the candidate's pinned customization policy, not a DPU configuration export. |
| `ovs/init-policy.json` | Illustrative global OVS settings and temporary bridge datapath. Review against the agreed candidate/deployment policy; no fallback to observed settings. |
| `pci/expected-pci.tsv` | Illustrative two-function BF3 profile. Confirm PCI addresses, IDs and bindings against the reviewed target hardware profile. |
| `management/expected-management.json` | Illustrates OOB and tmfifo driver identities; review against the required platform configuration. |
| `interfaces/expected-interfaces.json` | Two physical ports and two host-PF representors, matching the scope of the six-check trial. SF roles are intentionally absent from this example, so it cannot establish full representor coverage. |
| `network/maas-network-reference.yaml` | Synthetic MAAS Netplan format with dummy MACs and documentation IP addresses. Replace with the original MAAS-generated deployment reference. |

Not every expectation needs a file. The launcher supplies the expected kernel,
required package/module/hold lists, expected datasource and required tmfifo
address/prefix directly. Their authoritative sources and a full launcher example
are documented in the [provider README](../../README.md#running-the-smoke-plan).
The [complete launcher template](../../examples/smoke.launcher) includes all
inputs used by the current smoke selection.

## Real validation runs

Keep actual run inputs outside the source checkout, for example:

```text
~/bluefield-validation/<run-id>/
├── references/
│   ├── package-inventory.tsv
│   ├── expected-conflicts.tsv
│   ├── expected-pci.tsv
│   ├── expected-management.json
│   ├── expected-interfaces.json
│   └── maas-network-reference.yaml
└── checkbox.launcher
```

Prepare the references from the candidate build, reviewed hardware/topology
profile and original MAAS deployment configuration. Do not construct passing
expectations from observed DPU state. Automatic MAAS capture is not yet
implemented. Retain the same deployment reference across kernel updates/reboots.

Copy the launcher example from the provider README into the run directory and
replace all placeholders with absolute paths and reviewed expected values.
Retain the references and launcher with the reports at Checkbox's reported
output locations. This run-directory layout is a convention for this provider,
not a requirement imposed by Checkbox.
