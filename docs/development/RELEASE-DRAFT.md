# DevSift 0.1.16 candidate release notes

Candidate 0.1.16 makes ordinary installation and project lint ready to use:
verified native companions are installed and registered once, ordinary scans use
that user trust, and every case is delivered in a direct human `REPORT.md`.
It retains the complete sessions/pages introduced in 0.1.15.

The maintainer selected the next patch under the owner's continuing instruction
“ดำเนินการ released ขึ้น github เลยทันที”. The owner authorized continuing
publication without selecting this exact patch number. The intended tag is
`v0.1.16`; metadata/versioning is finalized by the release integration owner.
This is a candidate, not a publication receipt: final CI, platform companion,
artifact and release checks must pass before tag/publication.

## Changes

- Normal installation prepares four verified self-contained native helpers and
  registers their frozen manifest/digest in the fixed user scope. Scans, Doctor
  and CI use that registration without repeated native arguments. Explicit
  paired overrides still validate first; no target manifest is discovered.
- `devsift setup` registers an existing approved manifest or installs an explicit
  trusted offline companion; `setup --status` checks readiness without analysis.
  Registry corruption, changed pins or failed preflight never approve replacement
  bytes or silently activate a partial native configuration.
- Companion downloads are pinned to the CLI release version and platform. Their
  immutable SHA256-verified ZIP bytes undergo bounded path/type/layout validation,
  strict four-tool rebasing and readiness checks before launcher activation.
  Prior CLI activation is preserved on native preflight failure. Explicit
  `--core-only` discloses that code analyzers were not configured.
- Ordinary skill-driven project reviews choose whole-repository recommend mode;
  changed scope is reserved for explicit changes requests. The agent executes the
  authorized scan, reports actual coverage/findings/incomplete causes and next
  actions, and delivers a direct report link rather than a folder or JSON alone.
- `--report-language th|en` writes every case into session-root `REPORT.md`, with
  the path in `data.report_bundle.report`. Machine IDs, source proof and UNKNOWN
  states do not change with presentation language. Report publication journals
  ownership before atomic replacement and verifies report/page checksums.
- Canonical operator-home handling supports accepted macOS and Windows aliases
  while retaining protections inside DevSift-owned paths. Deep Windows report
  paths use normalized containment without changing global long-path policy.

## Candidate evidence and pending gates

Fresh ordinary Windows installation passed using a real embedded companion:
no `--core-only`, no SDK toolchains on PATH and no native flags on the subsequent
scan. All four language samples executed real native helpers, returned four
source-VERIFIED cases and a full Thai report; target source/Git data stayed
unchanged. This acceptance run took 89.102 seconds. It proves that tested
installation/sample set, not universal language or rule coverage.

The configured helpers cover C#, SQL, Go and TypeScript/JavaScript according to
their rules. Python quality coverage is not added. Setup `analysis_ready` means
configured native providers are ready; Doctor may remain overall incomplete for
an unsupported language while an eligible project can still be analyzed.

The release plan contains six companion ZIP/checksum pairs: Windows, Linux and
macOS, each x64 and arm64. Build, immutable source/version/pin checks, archive
inspection, installation and applicable execution validation must be recorded for
each published asset. Cross-building a file is not native execution evidence.
The final full suite, installed CLI, installer/rollback and platform CI gates are
pending at preparation time. Do not describe every platform as passed or the
candidate as published before those receipts exist.

## Use after installation

```text
devsift setup --status
devsift doctor
devsift scan --all --legacy-mode recommend --summary --report-language th
```

Open `data.report_bundle.report` for the complete human report. Read every case
page and preserve `reports_complete` separately from `analysis_complete`.
Unavailable tools, parser/process failures or unresolved source remain explicit;
exit 2 is an incomplete result, never a clean lint. Summary `findings: []` omits
the full array; use `data.finding_count` for the actual total.

## Distribution and boundaries

Installation requires Python 3.12+. Source/Git proof also needs trusted Git.
Companions provide their .NET/Node runtimes and compiled Go helper; consumers do
not need those development SDKs. The wheel alone remains CLI-only. The installer
may download a missing version-pinned companion during authorized setup; ordinary
scan/Doctor/CI never download, build or install tools or target dependencies.

The standard CLI/skill/source artifacts are accompanied by the six planned
platform ZIPs and their checksums. Bind the final artifact inventory/SBOM to the
reviewed source and include runtime/dependency and applicable notice evidence
for the actual companion payloads. Do not substitute the old core-only inventory
for an audit of bundled third-party runtimes.

The project license remains unselected (`NOASSERTION`). SHA256 records provide
integrity without a signature claim. Existing release-checker review/incomplete
outcomes stay visible; a digest or passing test is not a blanket security or
license approval. Previous releases/tags remain historical and are not moved.
`report --latest` and automatic `explain` storage remain pending. Live loading in
every AI host and native execution on every platform/architecture must not be
claimed without actual evidence. No scan or report authorizes source remediation.
