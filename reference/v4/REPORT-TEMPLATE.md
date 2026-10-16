# Full Quality Scan Report — <run-id>

## Run metadata
Repository: <repo> | Commit: <sha> | Merge base: <sha> | Policy: <version> | Scope: <scope> | Completeness: <complete/incomplete> | Analyzer versions: <versions>

## Summary and index
Blocking new: <n> | New warnings: <n> | Legacy advisory: <n> | Source unresolved: <n> | Tool failures: <n>
Each case ID links to the FULL case below. Never summarize away any finding.

## CASE <id> — <title>
- Rule / severity / confidence / detector: <...>
- Status: NEW / MODIFIED_INTRODUCED / MODIFIED_PREEXISTING / LEGACY_UNCHANGED / UNKNOWN
- Decision: BLOCK_NEW / ADVISORY / SECURITY_REVIEW / APPROVED / DEFERRED
- Source: `<repo>/<relative path>:<start line>:<column>-<end line>` OR `SOURCE_UNRESOLVED`
- Symbol: <namespace.class.method>; Git permalink: <verified immutable URL or unavailable>
- Related locations: <config/consumer/tests or not verified>
- Evidence provenance: <source/log/static/dynamic>; exact evidence with timestamp/line

### Current code (BEFORE — verified source only)
```<language>
<exact source with line numbers and issue marker; REDACT secrets>
```
**Root cause and human explanation:** <plain language, precise why, false-positive caveats>

### Proposed code (AFTER — proposal, not applied)
```<language>
<minimal proposed change or unified diff; if no verified source, write NOT AVAILABLE>
```
**Change scope / alternative / do not change:** <...>

### Effect if NOT changed
- Functional: <rating + evidence>
- Production diagnostics: <rating + evidence>
- Security: <rating + evidence>
- Frequency / affected endpoints: <measured or UNKNOWN>

### Risk IF changed
- Behavior / performance: <rating + evidence>
- Logging consumers and alerts: <rating + evidence>
- Trace continuity: <rating + evidence>
- Blast radius: <rating + evidence>
- Overall uncertainty: <...>

### Validation and rollback
Tests: <specific> | Before/after evidence: <specific> | Rollback: <specific>

### Prompt: REVIEW ONLY (copy/paste)
Review only case <id> at immutable commit <sha>, starting at <verified location or log evidence>. Verify source and related consumers. Evaluate before/after proposal and both effect dimensions. Preserve behavior and tracing. Do not edit any code. Return a bounded diff proposal, validation and rollback plan.

### Prompt: IMPLEMENT (copy/paste; only after explicit case approval)
Implement ONLY approved case <id> at <sha> within <files/symbols>. Use the approved minimal change; preserve contracts and existing correlation IDs. Run specified tests and consumer checks. Provide actual diff and before/after evidence. Stop if scope/risk changes; never fix other findings.
