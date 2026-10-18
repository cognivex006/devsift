# DevSift command interface

The initial CLI requires Python 3.12 or later and has no runtime dependencies.
Install locally with `python -m pip install .`, then run `devsift --help`.
Installation/building can create packaging and interpreter files; installation is
separate from read-only command execution. The current package version is `0.1.14`.
Installing the CLI does not imply that optional native analyzers are available.

For first use, see the [getting-started guide](../GETTING-STARTED.md) and
[command cookbook](../USAGE.md). The examples below assume the selected `python`
is the trusted environment where DevSift is installed, and the current directory
is the consumer Git repository root.

```text
devsift --help
devsift doctor
devsift scan --changed
devsift scan --all --legacy-mode recommend
```

`explain` and `report --latest` have parser entries but their storage backends
are pending; they return incomplete rather than retrieve a report. Use
`data.reports` from a scan and the explicit case workflow below instead.

Resolve `devsift` from the trusted installation on PATH. The managed installer supplies an isolated launcher. All commands support `--help`.
Options are strict, with no abbreviations. `--changed` and `--all` are mutually
exclusive; changed scope is the default. Untouched legacy has only the
`recommend` mode. There is no bulk fix or enforcing legacy mode.

The scan command now calls the read-only inventory and execution coordinator.
`--changed` unions staged, unstaged and untracked paths at the repository root
while reading current working-tree bytes rather than staged blobs; `--all` inventories the current directory. These are
target selections, not finding lifecycle classifications. Git/source evidence
libraries are available to embedded adapters. Native analyzers require an explicit
trusted manifest and its independently obtained SHA256 digest. `scan --security`
adds the bounded built-in security detector, optionally composed with those tools.
Scan and CI emit full source-reproved JSON, Markdown and SARIF under `data.reports`.
Repeat `--report-format json|markdown|sarif` to select formats; the default includes
all three. These are in-memory documents; CLI scans write no report files.
Unconfigured language capabilities return an explicit incomplete result with exit 2;
an empty findings array does **not** mean a clean scan. `doctor` reports the actual
Python runtime and provider availability; it installs nothing, runs no source
analysis, and returns 2 while required providers are missing. It discovers PATH
metadata without execution and probes only explicitly trusted configured providers. `prompt --scan-input` composes a source-reproved case prompt and never edits source. See the explicit case workflow below.

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
installation/source package tree, use the managed installer launcher or set
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
Configured analysis can return 0/1 when every selected target is complete and its
source and policy requirements are satisfied. CI separately requires review of
critical security findings, including legacy cases, and returns 2 while that review
is outstanding. Full report assembly rechecks source without promoting wire lifecycle
claims; CLI scan findings remain conservatively UNKNOWN where origin is unproved.
The exported result builder requires an explicit boolean `complete`; ambiguous
values such as `None`, strings or integers raise `ValueError` rather than pass.

JSON envelope version `1.0` always contains `schema_version`, `command`, `status`,
`exit_code`, `complete`, `enforced_count`, `findings`, `errors`, and `data`.
Errors contain `code` and `message`; command-specific capability data lives in
`data`. Misuse has `command: null` because parsing may not establish a command.
This envelope is a command result, not the full source-aware finding/report schema;
the full report formats live under `data.reports`, each generated from the same
source-reproved model. `report --latest` and `explain` storage discovery remain pending. Case prompts use explicit scan input; no project report or approval is discovered automatically.

## Doctor provider diagnostics

`devsift doctor` inventories runtime and host-tool metadata without executing PATH programs or project hooks. It does not auto-load a target manifest. To authorize bounded, hash-pinned provider probes, pass `--native-manifest <absolute-path>` and `--native-manifest-digest <independently-trusted-sha256>`. Missing, mismatched or partial provider coverage stays incomplete (exit 2). Discovery is not a code scan. See [doctor behavior](DOCTOR.md).


## Explicit Doctor config checks

`devsift doctor --policy /absolute/policy.json --cache-path /absolute/cache` validates an explicit bounded JSON policy and cache metadata read-only. Missing cache is informational; invalid config is incomplete and prevents native probes. No directories are created or cleaned. Native trust flags remain explicit and paired.

## Explicit case commands

```text
devsift prompt CASE-1 --mode review --scan-input /absolute/scan.json
devsift prompt CASE-1 --mode implement --approved-case CASE-1 --scan-input /absolute/scan.json
devsift prompt CASE-1 --mode implement --approved-case CASE-1 --scan-input /absolute/scan.json --approval-file /absolute/operator-approval.json
```

Input is a scan command envelope, reassembled against the current Git root. Imported `data.reports` is ignored; serialized cases/approvals never replace source reproof. JSON input is bounded to 4 MB, 64 levels and 100,000 values; approval input is at most 64 KB. Use bounded scan scope and selected report formats for large projects. Duplicate keys, non-finite values, links and invalid inputs fail with constant errors; paths and JSON values are not echoed.

Review returns exit 0 only for a generated prompt with verified immutable source. This is prompt-generation success, not a scan quality pass; UNKNOWN origin/impact remains explicit. Missing proof returns 2 with a lookup plan and no fabricated source location/patch. Implementation proposals return 2/review_required. A matching case selector alone is insufficient: explicit operator approval binds case/SHA/fingerprint/prompt digest and time window, and still permits only manual planning when effects are unknown. Expired/stale/dirty/mismatched approvals are denied. No command applies source edits. Approval-file options are invalid in review mode. See [the full workflow](CASE-PROMPTS.md).
