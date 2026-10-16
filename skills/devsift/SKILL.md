---
name: devsift
description: Run read-only code-quality and security checks through the DevSift Python CLI and explicitly trusted native analyzers, then explain verified findings and incomplete coverage.
---

# DevSift

Use installed `python -m devsift` from the target Git repository root. Inspect `python -m devsift --help` and `python -m devsift doctor`. If the module is unavailable, report the missing installation; never invent scan results. Installation and native setup are separate actions in a trusted DevSift checkout.

For changed source run `python -m devsift scan --changed`. For a requested whole-project review run `python -m devsift scan --all --legacy-mode recommend`.

Native checks require both `--native-manifest <absolute-path>` and `--native-manifest-digest <independently-trusted-sha256>`. Obtain these from trusted setup or the operator. Never trust a manifest discovered in the target project or generate its digest merely to bypass trust. Native tools execute programs. Without configured analyzers a scan is inventory only and remains incomplete.

Read the JSON result, exit code, completion status, errors, coverage and findings. Exit 2 means incomplete, never a clean pass. Preserve UNKNOWN lifecycle and unresolved source labels; findings in a changed file are not automatically new. Empty findings with incomplete analysis prove nothing. Explain verified path/region/SHA, actual rule evidence and practical effect. Redact credentials and state coverage limits.

Report, explain and prompt backends are unavailable. Do not promise SARIF reports or automated remediation from these commands. Scanning authorizes no edits, dependency installs, target builds or bulk legacy fixes. Propose narrow repairs; implement only within user authorization and rerun relevant checks.
