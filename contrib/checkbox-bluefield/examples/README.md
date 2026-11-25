# Launcher example

[`smoke.launcher`](smoke.launcher) selects the complete current smoke plan.
Copy it outside the checkout and replace every `REPLACE_WITH` placeholder using
independent device/software/deployment references. File paths are absolute paths
on the tested device; environment-variable expansion in values is not assumed.
The forbidden boot-argument list may be empty when no exclusions are required.

Input formats: [provider README](../README.md#input-formats) and
[reference examples](../checkbox-provider-bluefield/data/README.md).
Real candidate inputs and run results remain outside this repository.

```bash
checkbox-cli launcher /absolute/path/to/smoke.launcher
```

For focused debugging, add a `match` expression under `[test selection]` in a
copy of this launcher. Keep the unfiltered launcher for the integrated run.
