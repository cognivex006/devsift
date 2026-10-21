# DevSift command interface

The initial CLI requires Python 3.12 or later and has no runtime dependencies.
Install locally with `python -m pip install .`, then run `devsift --help`.
Installation/building can create packaging and interpreter files; installation is
separate from read-only command execution. The current package/plugin version is `0.1.16`.
A wheel-only installation provides the CLI; the normal installer additionally
deploys and registers the verified native companion. See [installation](../INSTALL.md).

## Registered lint and human report (0.1.16+)

DevSift 0.1.16 adds `setup` and `--report-language en|th`; check installed help
before using them with an older release. A normal authorized installer deploys
and registers its verified platform analyzer companion. An operator can instead
register an existing reviewed manifest once:

```text
devsift setup --native-manifest ABSOLUTE_MANIFEST --native-manifest-digest TRUSTED_SHA256
devsift setup --status
devsift doctor
devsift scan --all --legacy-mode recommend --summary --report-language th
```

`setup --analyzer-bundle ABSOLUTE_ZIP --bundle-digest TRUSTED_SHA256` installs an
explicit verified offline companion and registers it. Setup is a write operation;
`setup --status` reads readiness only. Registration lives in the fixed user scope
`~/.local/share/devsift/analyzers.json`, never a target-discovered configuration.
Scan, Doctor and CI resolve that trust by default. Explicit manifest/digest flags
remain paired, override registration for that invocation and validate first.
They do not change registration. Invalid explicit trust does not silently fall back.

`--report-language th` or `en` selects the human report language for scan/CI.
The direct file path is `data.report_bundle.report` (`REPORT.md` in the session
root); indexes and all case pages remain available for integrity/source evidence.
The language changes presentation, not identifiers, locations, source proof,
severity or gate decisions. Resume uses the same language/configuration.

An ordinary skill-driven project review chooses `--all --legacy-mode recommend`;
`--changed` is for an explicit changes request. This is a skill intent policy, not
a change to the CLI's parser default below. See [getting started](../GETTING-STARTED.md).

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
libraries are available to embedded adapters. Native analyzers require trusted
manifest/digest registration or an explicit pair. Published releases through 0.1.15
require the explicit pair; current registry resolution is described above. `scan --security`
adds the bounded built-in security detector, optionally composed with those tools.
Scan and CI produce full source-reproved JSON, Markdown and SARIF reports.
Small runs include them under `data.reports`; complete report indexes cover large runs.
Repeat `--report-format json|markdown|sarif` to select formats; the default includes
all three. In the 0.1.15 complete-run workflow, scan/CI process one file at
a time and create owned resumable sessions and report pages outside source.
Small results retain inline `data.reports`; large results expose the complete
`data.report_bundle` index. `--summary` returns compact counts and that index,
not the full target/finding arrays. Use `data.finding_count` for the total.
See [complete scans](../COMPLETE-SCANS.md) for `--report-dir`, `--resume`,
artifact verification and every-case reading. These options require the
0.1.15 or later; the published 0.1.14 did not provide them.
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
Scan/CI/Doctor/case prompts do not write consumer source/configuration or install dependencies.
Explicit installer/setup operations may prepare verified DevSift companions and user registration.
Scan/CI write only their owned session/report directory outside source;
Doctor and case-prompt commands do not create those sessions.
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
small full report formats live under `data.reports`; complete paged formats
live at `data.report_bundle`. In the new human-report workflow, `report` points
directly to `REPORT.md`; a summary's empty finding array is not zero cases.
Deliver actual executed coverage, finding count, incomplete causes, next action
and this direct report link. Every page contains a bounded `scan.json` for
case prompts. `reports_complete` means every requested case/page artifact is
present and verified; `analysis_complete` remains independent and may be false.
`report --latest` and `explain` automatic discovery remain pending. Case prompts
use explicit scan input; no project report or approval is discovered automatically.

## Doctor provider diagnostics

`devsift doctor` inventories runtime/host metadata and, in the new source CLI,
probes providers resolved from explicit paired flags or user registration. It
does not execute untrusted PATH programs, load target manifests, install tools or
analyze source. Missing/mismatched/partial coverage stays incomplete (2); ready
providers do not prove a clean source scan. See [doctor behavior](DOCTOR.md).


## Explicit Doctor config checks

`devsift doctor --policy /absolute/policy.json --cache-path /absolute/cache` validates an explicit bounded JSON policy and cache metadata read-only. Missing cache is informational; invalid config is incomplete and prevents native probes. No directories are created or cleaned. Native trust comes from user registration or an explicit paired override.

## Explicit case commands

```text
devsift prompt CASE-1 --mode review --scan-input /absolute/scan.json
devsift prompt CASE-1 --mode implement --approved-case CASE-1 --scan-input /absolute/scan.json
devsift prompt CASE-1 --mode implement --approved-case CASE-1 --scan-input /absolute/scan.json --approval-file /absolute/operator-approval.json
```

Input is a scan command envelope, reassembled against the current Git root. Imported `data.reports` is ignored; serialized cases/approvals never replace source reproof. JSON input is bounded to 4 MB, 64 levels and 100,000 values; approval input is at most 64 KB. Use bounded scan scope and selected report formats for large projects. Duplicate keys, non-finite values, links and invalid inputs fail with constant errors; paths and JSON values are not echoed.

Review returns exit 0 only for a generated prompt with verified immutable source. This is prompt-generation success, not a scan quality pass; UNKNOWN origin/impact remains explicit. Missing proof returns 2 with a lookup plan and no fabricated source location/patch. Implementation proposals return 2/review_required. A matching case selector alone is insufficient: explicit operator approval binds case/SHA/fingerprint/prompt digest and time window, and still permits only manual planning when effects are unknown. Expired/stale/dirty/mismatched approvals are denied. No command applies source edits. Approval-file options are invalid in review mode. See [the full workflow](CASE-PROMPTS.md).

## Third-party terms (0.1.17+)

`scan`, `ci` and `doctor` accept `--terms-catalog ABSOLUTE_JSON` plus
`--terms-catalog-digest TRUSTED_SHA256`. Both or neither; scan/CI always assess
terms. No waiver/disable flag. Doctor checks configuration only.

`devsift terms check` assesses terms and writes the complete human report without
native analyzers; supports the same catalog pair, `--summary`, `--report-dir`,
`--resume`, `--report-format` and `--report-language th|en`.
`devsift terms history` reads verified durable decisions.
`devsift terms decide CASE_ID --choice remediate|decline|reconsider|resolved
--owner ACTUAL_OWNER --reason EXPLICIT_REASON --fingerprint CURRENT_FINGERPRINT
--evidence-digest CURRENT_EVIDENCE_DIGEST` takes the same catalog pair.
`reconsider` requires `--supersedes PRIOR_EVENT_ID`. A successful write does not
clear the gate; inspect `data.decision_recorded` even when exit is 1 or 2.

See [third-party terms](../THIRD-PARTY-TERMS.md) for schema, scope, trust and memory.
