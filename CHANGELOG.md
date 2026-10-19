# Changelog

All notable user-facing changes to DevSift will be documented here. This follows Keep a Changelog conventions; Specification v6 is **not** a released software version.

## [Unreleased]

## [0.1.16] - 2026-10-19

### Changed
- Route ordinary AI project reviews to full-repository lint, use registered user analyzer trust, and deliver analyzer coverage, actionable next steps and the direct human report link.
- Document one-time `setup` registration/status, verified platform companion installation and language-specific full `REPORT.md` delivery for version 0.1.16; keep scanning free of automatic downloads or builds.
- Install and verify the platform's self-contained C#, SQL, Go and JavaScript/TypeScript analyzers before activating a normal installation; persist operator-approved analyzer pins for plain `scan` and `ci` commands.

### Fixed
- Produce a complete English or Thai `REPORT.md` with verified source locations and per-case next actions, including JSON-only report requests; retain honest incomplete coverage when an analyzer cannot run.
- Recover interrupted report publication through a durable ownership journal while refusing foreign replacements, links and hardlinks.
- Create and resume deep Windows scan/report storage without requiring system-wide long-path policy changes.

## [0.1.15] - 2026-10-18

### Added
- Process CLI scans/CI one immutable source snapshot at a time, with private disk-backed sessions, cancellation/resume, current analyzer readiness checks and changed-source revalidation.
- Produce every case across adaptive source-reproved report pages with complete indexes, checksums and separate report/analysis completion; add `--report-dir`, `--resume` and compact `--summary` output.
- Support private native source/diagnostic file transport for all four helpers without aggregate inline size or finding-count caps, plus explicit wait-until-completion execution.
- Stream large immutable source proof with exact UTF-8, region and Git blob checks; preserve whole-excerpt masking and source/target read-only boundaries.
- Display full-run stages in two in-place stderr rows with elapsed time and cancellation cleanup; retain clean redirected JSON.

### Fixed
- Mask scanner targets/findings independently so repository cardinality cannot exhaust one cumulative redaction budget; retain all per-item safety checks.
- Exclude per-file inventory from formatted-report assembly input without removing it from CLI coverage output.
- Preserve already-redacted scan findings, counts and errors when a fresh CLI report cannot render; return incomplete with `REPORT_UNAVAILABLE` instead of discarding the scan.

## [0.1.14] - 2026-10-18

### Fixed
- Preserve large repository scan coverage and reports by using a bounded generated-output redaction budget; keep generic input limits, secret masking, cycles and collision checks intact.
- Deduplicate fixed scanner error categories without dropping per-file outcomes or counts, avoiding report rejection on many unavailable files.
- Resolve consumer skill references from the loaded plugin/skill directory and report actual incomplete JSON results instead of stopping at an execution plan or dumping a truncated inventory.

## [0.1.13] - 2026-10-18

### Changed
- Reserve two in-place terminal rows for installer/update/setup feedback, with a rotating spinner, measured download percentages and separately labelled overall milestones; keep redirected stages bounded and JSON transport clean.
- Generate all four install/update variants from two templates and embedded renderer sources; test native ConPTY/POSIX screen states and narrow terminals.
- Require download feedback in repository development instructions and add it to schema/native setup workflows.

### Fixed
- Repair Windows PowerShell 5.1 Python detection in install/update bootstraps and continue past broken PATH candidates; exercise the downloaded scripts through `irm | iex` in real legacy PowerShell.

### Added
- Repository marketplace catalogs for Claude Code, Copilot and Cursor, a portable root plugin manifest, Copilot standalone skill deployment, and remote installation instructions for all supported hosts with public-listing limitations.
- A visible full report template and illustrative incomplete report, bundled with the consumer skill and linked from report workflows; explain extracting Markdown from the JSON envelope.

## [0.1.12] - 2026-10-17

### Fixed
- Accept actual Windows 8.3 root/policy/cache aliases in read-only Doctor diagnostics after original-component link/reparse checks, retaining canonical root containment and descriptor identity protection.

### Changed
- Separate user guides, consumer reference and developer documentation; remove planning identifiers from product documentation and use `devsift` in command examples.
- Reorganize consumer documentation around Thai first-use, separate CLI/skill installation, everyday commands and troubleshooting; correct stale Doctor flag and pending report-storage examples.
- Expose read-only Doctor config/cache flags and explicit case-input review/proposal commands with bounded JSON, exact operator binding and no automatic source writes. Consumer skill invokes the installed CLI.
- Add read-only Doctor provider discovery with explicit native-manifest trust, bounded probes, actionable missing-tool diagnostics and matching CLI flags.
- Assess finding origin with verified Git provenance, reviewed baselines and expiring waivers while preserving unknown business impact and independent security review.

- Moved specifications, plans and maintainer orchestration to devsift-specs. Kept the consumer skill and runtime, replaced plan CI with runtime tests, and documented actual CLI capabilities.

- Development jobs use ignored `worktrees/<job>` inside the source repository; finished integrated or superseded folders are removed while preserving commit refs and cleanup evidence.
- Published and independently verified the initial 160-file scaffold; historical planner tests now tolerate execution progress.
- Documentation, task ownership, paths and prompts now consistently reference `orchex006/devsift` rather than a generic quality-lint repository.
- Brand-independent adapters: integration with AgriMap, Drevqon, Axiom is optional, not mandatory.

### Added
- Windows/POSIX install and update scripts, private CLI environments, release-asset preparation, and portable offline consumer skills for Codex, Claude Code, Gemini CLI, Antigravity and Cursor with host plugin manifests.
- Deterministic commit-bound source ZIP bundles with independently trusted integrity checks; actual offline wheel/sdist fresh-install and explicit rollback proof runs on Windows and Linux.
- Bounded read-only ZIP/wheel secret-shape inspection with full stored/deflate payload integrity checks; incomplete and review results never grant publication authority.
- Explicit component allowlists and audited wheel/sdist inputs, excluding unlisted source and maintainer assets.
- Bounded repository-local policy discovery with protected reads and Git metadata alias rejection.
- Fresh source-bound security escalation independent of quality thresholds, preserving incomplete configured-provider failures and unknown impact.
- Executable report walkthrough and read-only onboarding for new changes and existing codebases.
- Explicit maintainer/consumer boundaries, compact specifications-owned task templates and isolated installed-CLI governance fixtures.
- Planning-only change budgets and immutable Git diff measurements with bound declared diagnostic/regression/rollback evidence; these never authorize remediation.
- Source-reproved full JSON, Markdown and SARIF in scan/CI output, with explicit format selection, safe CI annotations and an outside-source artifact writer.
- Source-linked candidate consumer/test context and mixed baseline gates, preserving unknown effects and pending case approval.
- Windows/Linux report workflow with exact-key NuGet-only cache restoration, protected main-branch cache saving and deterministic report artifacts.
- Conservative credential/security-context analysis and structured observability recommendations with unknown impact and consumer evidence preserved.
- Fresh read-only CI entry with pinned-manifest authorization, immutable snapshot checks, actual Git source attribution, supported severity thresholds and independent security-review gating.
- Immutable source-reproved report assembly with conservative lifecycle trust, explicit unknown impact/consumer evidence, pending proposals and case-scoped read/implement guidance.
- Reviewed immutable baseline approval/CAS and owner-ticket-expiry waivers, including fail-closed critical-security policy.
- Bounded native process/protocol host and actual pinned Roslyn, Go AST, ESLint/TypeScript and ScriptDom rules with positive/negative source fixtures.
- Explicit trusted manifest/digest flags enable native CLI scans with immutable source proof and conservative UNKNOWN lifecycle gating.
- Explicit pinned native helper setup and Windows/Linux CI running actual Roslyn, Go AST, ESLint/TypeScript and ScriptDom tests.
- Immutable Git merge-base/fingerprint/rename-region provenance with explicit UNKNOWN for ambiguous history or origin.
- Trusted adapter execution and conservative aggregation connected to CLI inventory, including filter-free staged/unstaged/untracked scope selection.
- Immutable Git-backed source evidence, distinct runtime/proposal contracts, strict wire schemas and full-context snippet redaction.
- Deterministic read-only source inventory and explicit adapter capability negotiation; unavailable analyzers never imply clean analysis.
- Installable Python CLI shell with strict commands, JSON error envelopes and exit codes 0/1/2/3; unavailable analyzer/report capabilities remain incomplete.
- Strict policy v1 overlays and immutable 23-rule severity registry, with evidence-aware legacy/unknown enforcement and independent critical-security review.
- DevSift brand, canonical repository URL, scoped maintainer and consumer skill identities.
- First-run bootstrap for the initial repository scaffold and GitHub description.
- Independent bootstrap verification, offline kit validation and Linux/Windows checks.

### Security
- Credential findings withhold the entire verified source region through native output, scanner reproof, classifier and baseline capture; raw-content fingerprints remain distinct.
- Windows process-assignment failures terminate the owned suspended child; baseline aliases share canonical CAS locks without allowing symlink/junction parents.
- Initial remote bootstrap prohibits force push, secret publication, unreviewed license selection and writes to non-target repositories.

- Add a read-only release-candidate readiness check that composes trusted-pin source-bundle verification with bounded archive inspection while retaining release blockers.
- Add an unreleased release-notes draft and release preparation checklist covering four source components, candidate-derived SBOM/license evidence, and pending owner approval.
