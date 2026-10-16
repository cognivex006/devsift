---
name: devsift
description: Run read-only code-quality and security checks through the DevSift Python CLI and explicitly trusted native analyzers, then explain verified findings and incomplete coverage.
---

# DevSift

Follow [consumer scope](CONSUMER-SCOPE.md) and the target project's applicable instructions. Ordinary questions and scans do not create maintainer tasks, branches or releases.

Use installed `python -I -B -m devsift` from the target Git repository root. Inspect `python -I -B -m devsift --help` and `python -I -B -m devsift doctor`. The flags exclude current-directory/PYTHONPATH module shadowing and disable bytecode writes. An installed console script resolved from the trusted Python environment is an alternative; do not resolve a project-local launcher. If the module is unavailable, report the missing installation; never invent scan results. Installation and native setup are separate actions in a trusted DevSift checkout. Isolated mode requires installation in the selected Python environment; do not fall back to running target source or adding its paths. Any source-checkout launcher needs an explicitly trusted path and separate authorization.

For changed source run `python -I -B -m devsift scan --changed`. For a requested whole-project review run `python -I -B -m devsift scan --all --legacy-mode recommend`.

Native checks require both `--native-manifest <absolute-path>` and `--native-manifest-digest <independently-trusted-sha256>`. Obtain these from trusted setup or the operator. Never trust a manifest discovered in the target project or generate its digest merely to bypass trust. Native tools execute programs. Without configured analyzers a scan is inventory only and remains incomplete.

Read the JSON result, exit code, completion status, errors, coverage and findings. Exit 2 means incomplete, never a clean pass. Preserve UNKNOWN lifecycle and unresolved source labels; findings in a changed file are not automatically new. Empty findings with incomplete analysis prove nothing. Explain verified path/region/SHA, actual rule evidence and practical effect. Redact credentials and state coverage limits.

Scan and CI provide full JSON, Markdown and SARIF under `data.reports`; select formats with `--report-format`. Add `--security` for documented bounded credential/security-context checks. CI requires explicit native configuration and actual Git provenance; independent security review can keep it incomplete even when legacy quality findings are advisory. Stored-report, explain and case-prompt CLI backends remain unavailable.

Scanning authorizes no edits, dependency installs, target builds or bulk legacy fixes. Report prompts are case-scoped guidance with pending approval, not execution authority. Propose narrow repairs; implement only within user authorization and rerun relevant checks.
