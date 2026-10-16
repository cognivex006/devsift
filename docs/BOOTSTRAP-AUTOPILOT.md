# DevSift — Autonomous first-repository bootstrap runbook

> Intended for **T000** only. This is a future execution runbook; merely opening it or running the planner does not mutate GitHub. Do not use it on other repositories.

## Target and exact Description

- Repository: `https://github.com/orchex006/devsift` (public); default branch observed `main`; as of 2026-10-16, no Git objects and Description null. **Recheck before writes.**
- Description: `DevSift is a language-agnostic code quality toolkit for change-aware analysis, source-linked diagnostics, risk-aware remediation, and automated quality gates.`
- Suggested topics after initial bootstrap: `code-quality`, `static-analysis`, `linting`, `developer-tools`, `quality-gates`, `ai-assisted-development` (optional; do not block bootstrap if unsupported).
- Product status: planning/bootstrap. Do not describe the lint engine as released or functional. No tag or release.

## One-command guarded bootstrap (preferred)

Once an executing agent has the approved extracted kit in a clean staging directory and actual GitHub credentials, use:

```bash
python tools/bootstrap_repo.py
python tools/bootstrap_repo.py --apply --confirm-repo orchex006/devsift
```

The first command is a **read-only dry run**; the second performs the initial commit/push and repository metadata edit only after an exact owner/repository confirmation and remote-empty preflight. It checks the kit, test suite and staged file manifest. An interrupted partial publish must be diagnosed and resumed manually at the completed Git SHA; it must **not** be force-retried against a nonempty remote. See all underlying steps below.

## Controller autopilot procedure

1. Check host credentials: `gh auth status`, `gh repo view orchex006/devsift --json name,description,defaultBranchRef,isPrivate`. Verify `gh api repos/orchex006/devsift` and `git ls-remote https://github.com/orchex006/devsift.git`; **zero refs only**, otherwise stop (the repo is no longer empty).
2. Assemble exact approved v6 tree in a **new clean staging directory**. Stage the **contents of the `devsift/` kit root** (not its enclosing folder, archive or user downloads). Ensure the final repository root includes README.md, AGENTS.md, DEVELOPMENT.md, CHANGELOG.md, plan/, docs/, tools/, tests/, skills/, governance/, templates/, prompts/, integration/, reference/, .github/, etc.
3. Run `python tools/planctl.py validate`, `python -m unittest discover -s tests -v`, `python tools/validate_kit.py`. Verify all content is reviewable text, .gitignore excludes checkpoints/caches, source manifest files match. Secrets scan every publishable path; never upload user-local notes or credentials.
4. In this **verified empty** repository, initialize Git `main` with exactly one root commit (no unrelated local source or cached history). Example, from staging root:

   ```bash
   git init -b main
   git remote add origin https://github.com/orchex006/devsift.git
   git add -- README.md AGENTS.md DEVELOPMENT.md CHANGELOG.md CONTRIBUTING.md SECURITY.md .editorconfig .gitignore .github/ plan/ docs/ tools/ tests/ skills/ governance/ templates/ prompts/ reference/ integration/
   git diff --cached --check
   git diff --cached --name-only
   git commit -m "chore(repo): bootstrap DevSift governance and execution kit" -m "Refs: T000"
   git push -u origin main
   ```

   Paths above are the approved source scope; if the package adds more canonical files, verify them against a **reviewed file manifest** before staging. `git add -A` and force-push are forbidden. A rejected push is a blocker, not a reason to rewrite remote history.
5. Update repository Description using the available authenticated owner-capable client. With GitHub CLI:

   ```bash
   gh repo edit orchex006/devsift --description "DevSift is a language-agnostic code quality toolkit for change-aware analysis, source-linked diagnostics, risk-aware remediation, and automated quality gates."
   gh repo view orchex006/devsift --json description,defaultBranchRef --jq '{description,defaultBranch: .defaultBranchRef.name}'
   ```

   Only if permissions allow. If unsupported, report `METADATA_UPDATE_BLOCKED` and leave the task pending; never claim success. Do not substitute editing README for repository metadata.
6. Verify `git ls-remote` main SHA and a fresh GitHub contents/tree listing against the staged SHA256 manifest, and verify Actions status. An Actions workflow in the repository is not proof that Actions executed. Record SHA, exact file list, CLI output, remote Description, CI URL and any protection status.
7. Send to independent review (`in_review`). Only after a distinct reviewer verifies the remote artifact and metadata may the controller mark T000 `accepted`. Record checkpoint and dispatch eligible tasks T001/T002/T004/T005/T007/T008 and T076 as capacity/locks permit.

## Permissions and exceptions

A genuinely empty repository needs one initial root commit to establish `main`; this narrowly-scoped exception is not a standing bypass of branch protections. Future changes use short-lived branches and PRs. Publishing v6 planning docs is **not** a software release or authorization to auto-publish packages, create GitHub Releases, choose a legal license, or change organization/account settings. A public repository does not imply an open-source license has been granted; request an owner license decision before asserting one.

If the connected GitHub tool lacks repository Description update, use `gh repo edit` in the executing owner-authorized environment. Do not fabricate a successful edit. If any file already exists on remote, stop and reconcile the exact diff, do not blindly overwrite. Continue after checkpoints without losing evidence.

## Evidence template

`repo_url`, `default_branch`, `remote_empty_verified_at`, `source_manifest_sha256`, `initial_commit_sha`, `remote_main_sha`, `description_before`, `description_after`, `ci_run_url_or_not_run`, `branch_protection_verified_or_unknown`, `reviewer`, `review_result`, `rollback_strategy`, `next_step`.
