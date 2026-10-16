# DevSift command interface

The initial CLI requires Python 3.12 or later and has no runtime dependencies.
Install locally with `python -m pip install .`, then run `devsift --help`.
Installation/building can create packaging and interpreter files; installation is
separate from read-only command execution. `0.0.0.dev0` is an unreleased packaging
placeholder, not a release or a claim that an analyzer exists.

```text
devsift scan --changed
devsift scan --all --legacy-mode recommend
devsift explain OBS-001
devsift report --latest
devsift doctor
devsift prompt OBS-001 --mode review
devsift prompt OBS-001 --mode implement --approved-case OBS-001
```

`python -m devsift` provides the same interface. All commands support `--help`.
Options are strict, with no abbreviations. `--changed` and `--all` are mutually
exclusive; changed scope is the default. Untouched legacy has only the
`recommend` mode. There is no bulk fix or enforcing legacy mode.

The scan command now calls the read-only inventory and execution coordinator.
`--changed` unions staged, unstaged and untracked paths at the repository root
while reading current working-tree bytes rather than staged blobs; `--all` inventories the current directory. These are
target selections, not finding lifecycle classifications. Git/source evidence
libraries are available to embedded adapters. Native analyzers require explicit trusted manifest configuration;
report serialization/storage and case prompt backends remain pending.
Current requests return an explicit incomplete result with exit 2;
an empty findings array does **not** mean a clean scan. `doctor` reports the actual
Python runtime and provider availability; it installs nothing, runs no source
analysis, and returns 2 while required providers are missing. It discovers PATH
metadata without execution and probes only explicitly trusted configured providers. `prompt` validates per-case approval for
implement mode but cannot compose a verified prompt yet and never edits source.

Changed-scope queries disable effective Git clean/process/smudge filters and their
required flags as well as external diff/textconv/fsmonitor callbacks. Effective
driver names are read from Git configuration including global, worktree, included
and environment scopes, then overridden only for each query's subprocess. No
configuration file is modified and no filter command/value is printed. Source
Git configuration must remain stable while the query runs. Disabling conversions
can conservatively select additional normalized/LFS-managed files; inventory still
reads only current working-tree bytes and does not run conversion callbacks.

Successful help is text on stdout with exit 0. Other valid commands emit exactly
one JSON object on stdout. Misuse emits one JSON object on stderr, no stdout,
and exit 3. Argument errors avoid reflecting user input, which may contain secrets.
No command writes source, config, reports, application caches or installs dependencies.
Python can write the package initializer's bytecode before its code disables
further bytecode writes. For a strict no-write run that also includes the Python
installation/source package tree, use `python -B -m devsift ...` or set
`PYTHONDONTWRITEBYTECODE=1` before launching the console script. This matters when
running a cold source checkout located inside the target repository. Filesystem
tests cover both the target tree and a cold package tree with `-B`. External Python
startup hooks and build/install tools are outside this command's control.

| Code | Status | Meaning |
| --- | --- | --- |
| 0 | clean | Completed analysis with no enforced violations, or successful help |
| 1 | enforced | Completed analysis with verified enforced violations |
| 2 | incomplete | Missing capability, tool failure or unresolved analysis |
| 3 | misuse | Invalid command, option or approval argument |

Incomplete takes precedence over enforced violations; unknown never means pass.
A complete result with legacy security-review findings can return 0 while preserving
`security_escalation: true`; consumers must process that flag for independent review.
Codes 0/1 for analysis are exported via `devsift.output.result` for future engine
integration and contract tests. Current analysis commands cannot return them.
The exported result builder requires an explicit boolean `complete`; ambiguous
values such as `None`, strings or integers raise `ValueError` rather than pass.

JSON envelope version `1.0` always contains `schema_version`, `command`, `status`,
`exit_code`, `complete`, `enforced_count`, `findings`, `errors`, and `data`.
Errors contain `code` and `message`; command-specific capability data lives in
`data`. Misuse has `command: null` because parsing may not establish a command.
This envelope is a command result, not the full source-aware finding/report schema;
it must not be represented as SARIF or an authoritative scan report.

## Doctor provider diagnostics

`python -m devsift doctor` inventories runtime and host-tool metadata without executing PATH programs or project hooks. It does not auto-load a target manifest. To authorize bounded, hash-pinned provider probes, pass `--native-manifest <absolute-path>` and `--native-manifest-digest <independently-trusted-sha256>`. Missing, mismatched or partial provider coverage stays incomplete (exit 2). Discovery is not a code scan. See [doctor behavior](DOCTOR.md).
