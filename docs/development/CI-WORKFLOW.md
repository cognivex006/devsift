# Quality-gate workflow boundary

`.github/workflows/quality-gate.yml` runs on main-branch pushes and ordinary pull
requests targeting main. It never uses pull_request_target or workflow_run.
Analysis has a contents-read token, no persisted checkout credentials, full Git
history, and a 20-minute Windows/Linux matrix. Windows disables automatic CRLF
conversion before checkout during explicit runner setup so immutable HEAD proof
can match the actual checked-out bytes.

Pinned checkout/setup actions select Python 3.12, .NET SDK 9.0.205, Go 1.21.3
(implicit setup-go caching disabled) and Node 24. The explicit trusted
`tools/build_native.py` setup builds only DevSift's helpers and records the four
configured native tools; it is not a target-source build hook. The quality step
then invokes `tools/run_quality_ci.py` using a fixed absolute runner-temp output
directory outside the source checkout. PowerShell receives paths through runner
environment variables and explicitly returns the Python exit code. No PR title,
branch/ref name or other event text is interpolated into shell code.

The base commit is supplied only through DEVSIFT_BASE_SHA: the PR base SHA or push
before SHA. The invoked entrypoint validates immutable commit evidence and exact
source scope. Missing/unavailable/zero base does not silently mean NEW or clean;
finding attribution can remain UNKNOWN/incomplete. Enforced defects fail with 1,
missing/incomplete work with 2, completed nonblocking work with 0. The workflow
does not use continue-on-error to turn either failure into success.

## What this job actually covers

The controller's `tools/run_quality_ci.py` intentionally passes explicit tracked
production `devsift/*.py` paths to the read-only CI coordinator and Python security
rulepack, with the prepared native manifest/probes. This is not a claim that every
repository file or every C#/Go/TypeScript/SQL rule has been analyzed. Test fixtures,
helper projects, arbitrary consumer projects and unselected source trees are not
silently counted as covered. Scope metadata and complete reports disclose actual
paths, findings and unavailable work. Consumers can explicitly choose their own
supported scope/tool manifests; scanning never automatically builds target code.

## Complete artifacts and optional SARIF publishing

After analysis, an always-run artifact step saves exactly `report.md`,
`findings.json` and `results.sarif`, even when the quality step fails. The
controlled artifact name is `devsift-quality-<matrix OS>` and retention is seven
days. There are no source-tree globs or missing-file ignore behavior. If setup or
report generation failed before these files existed, artifact upload fails
explicitly; it does not fabricate successful artifacts or conceal the gate.

SARIF service publishing is **off by default**. Only repository variable
DEVSIFT_SARIF_UPLOAD set exactly to `true` permits the separate publisher job,
and only for a push or a pull request whose head repository is this repository.
Cancelled runs are excluded. Fork PRs cannot run this publisher. Failed quality
gates can still publish an available same-run SARIF artifact when these explicit
conditions are met; SARIF completeness/security flags remain in the document.

The publisher alone has security-events-write, alongside contents-read. It has
only three fully pinned external action steps: credential-free metadata checkout,
download of this run's fixed expected artifact to a fixed temporary directory,
and CodeQL SARIF upload of that exact results.sarif with an OS category. It runs
no shell steps, source code, installs, local repository actions or analysis under
the privileged token. There is no arbitrary run ID, external token, source-tree
SARIF path or event-controlled artifact lookup. The upload action is trusted
pinned tooling; this separation is not an OS sandbox or artifact authentication
against an authorized same-repository writer changing the whole workflow.

This document describes configured behavior, not proof that the optional external
SARIF service upload has occurred. Actual run/artifact evidence is recorded by
the controller after GitHub Actions executes the integrated pipeline. Default-off
publisher behavior must not be reported as a successful live upload.

`test_ci_workflow_contract.py` parses actual YAML using pinned development PyYAML
and checks action SHAs, triggers, token scope, setup/scan order, immutable checkout,
fixed source/output boundaries, failure propagation, three artifact filenames,
same-run publisher restrictions and disabled-default opt-in. Negative mutations
must fail for privileged analysis, pull_request_target, moving action tags,
persisted credentials, shell event interpolation, swallowed gates, source globs,
missing-file ignores, fork/cancellation guard removal, arbitrary artifact run IDs
and privileged source execution. Runtime artifact generation/annotations are
tested separately by the controller; this workflow contract does not simulate
GitHub execution. See the bounded cache contract below.


## Locked package cache

Only `${{ github.workspace }}/.devsift/local/nuget` is cached. Restore and save
are separate actions pinned to `0057852bfaa89a56745cba8c7296529d2fc39830`.
PRs, including forks, restore only. Save requires successful analysis on a push
to `refs/heads/main`, an absent exact hit, and a nonempty primary restore key.
No publisher job uses a cache or gains cache-related permissions.

The exact key includes runner OS and architecture, SDK 9.0.205, Go 1.21.3,
Node 24, and a hash of native project/lock/config/build files, frontend lock,
Go module and development requirements. There are no prefix restore keys or
cross-OS archives. A miss is allowed; it never implies a successful analysis.
A key change creates a new cache namespace; this workflow provides no fallback
to older dependency inputs.

Every run still performs explicit trusted setup, SQL NuGet restore with
`--locked-mode` and lock content hashes, helper builds, pinned native probes,
and the source scan. Cache-hit values never skip those steps. Cache contents
are dependency acceleration, not analysis proof or a sandbox. No analyzer
binary, manifest, report, token or general home-directory cache is retained.
Setup uses the declared public NuGet source and never target-project hooks.

`test_ci_cache_contract.py` checks these exact boundaries and rejects broader
paths, fallback/cross-OS keys, moving pins, PR saves, widened token privileges,
cache-based build/scan skipping and privileged publisher caches. The actual
pipeline repeat fixture runs the same immutable HEAD/base twice into separate
output directories and byte-compares all three reports while preserving an
actual blocking exit code and unchanged source/Git bytes. Package-cache marker
availability must not affect those reports. Other actual pipeline fixtures
retain incomplete exit 2 and complete report artifacts. These tests run on the
runtime Windows/Linux matrix; local results do not prove hosted cache hits.
Hosted miss/hit/save behavior and both-platform success must be recorded from
real GitHub runs before making that claim. Rollback removes only the restore
and save steps; explicit setup and analysis continue without the cache.
