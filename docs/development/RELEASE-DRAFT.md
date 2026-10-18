# DevSift 0.1.15 release notes

DevSift 0.1.15 processes large scans through resumable private sessions and
produces every case across complete report pages. All four native helpers
support private source/diagnostic file transport, so repository inventories and
case counts do not inherit the old aggregate inline-document limits.

The maintainer selected `0.1.15` as the next patch under the owner's continuing
instruction “ดำเนินการ released ขึ้น github เลยทันที”. The owner authorized
publication of the continuing fixes, without selecting this exact patch number.
The intended tag is `v0.1.15`; package and agent plugin manifests use that version.
Final candidate review, checks and artifact verification still precede publication.

## Changes

- Analyze one immutable source snapshot at a time and persist only redacted
  results outside the target. Resume rechecks source, scope/configuration and
  current analyzer trust/readiness; changed or incomplete targets run again.
- Render all cases across adaptive JSON, Markdown and SARIF pages with indexes,
  checksums and bounded per-page `scan.json` inputs for case prompts. Report
  integrity/completeness is separate from analyzer/source completeness.
- Add `--summary`, `--report-dir` and `--resume`; full JSON still streams every
  target and finding. Summaries disclose fresh versus reused targets.
- Support all four native helpers with private file transport and explicit
  wait-until-completion execution. Preserve integrity pins, subprocess cleanup,
  cancellation and finite standalone Doctor probes.
- Stream large immutable Git source proof and mask oversized excerpts while
  retaining exact source identity/regions and every case.
- Show real scan stages in two in-place stderr rows; restore the console on
  success, failure and cancellation. Redirected JSON stays free of animation.
- Preserve independent security-review metadata across cache reuse and remove
  obsolete metadata when the originating target disappears. Neither scanning
  nor case-prompt generation grants source-edit permission.

## Verification and honest coverage

The real user repository retained all 8,209 inventory targets and 467 native
calls, with full reports for all 10 returned cases. `reports_complete` was true;
analysis remained incomplete where parser/source proof was unresolved. The target
source was unchanged. These counts are evidence for that run, not a claim that
all source or every rule was verified clean.

The four real native helpers were exercised with source larger than 2.1 MB and
more than 1,000 diagnostics each. The report pipeline rendered all 1,205 fixture
cases in all requested formats, including case-prompt input pages. Windows
ConPTY checks covered 40, 48, 80 and 120 columns, resize and cancellation.
Record final candidate-matched CI, package/install/rollback results and artifact
hashes in the release receipt; this draft does not turn pending checks into passes.

## Distribution and limitations

Python 3.12 or newer is required. Native analyzer binaries are not bundled;
trusted native setup is separate. A parser/process failure or unresolved source
still means incomplete analysis and exit 2. No target code is built, installed or
modified. Persisted `report --latest` and `explain` backends remain unavailable;
read the owned report indexes and use a page's `scan.json` for case prompts.
Live loading in every AI host has not been verified.

The project license remains unselected; no new license is declared and artifact
inventory records `NOASSERTION`. SHA256 files provide integrity checks without
claiming cryptographic signatures. Separately installed optional native
components have their own dependency/setup evidence. Release assets include the
installer bundle/scripts, wheel, source distribution, consumer/source components
and source/integrity records.
