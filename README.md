# DevSift

A code-quality skill backed by a read-only Python CLI and optional native analyzers for .NET, TypeScript, Go and SQL. The skill guides an agent to run checks and interpret source-linked findings.

## Use

Requires Python 3.12+. Install the package from a trusted checkout with `python -m pip install .`, and load [skills/devsift](skills/devsift/SKILL.md) in your agent host. Pip installs the CLI; the skill folder is installed separately in the host's skill directory.

From the target Git repository root:

```sh
python -m devsift --help
python -m devsift doctor
python -m devsift scan --changed
python -m devsift scan --all --legacy-mode recommend
```

A scan without configured native tools inventories source and returns incomplete. Actual analysis requires an explicitly trusted absolute manifest and independently trusted SHA256:

```sh
python -m devsift scan --changed --native-manifest /absolute/trusted-tools.json --native-manifest-digest <sha256>
```

Add `--security` for bounded credential and supported logging/TLS checks; see the
[security coverage](docs/SECURITY-ANALYSIS.md). Scan and CI include full JSON,
Markdown and SARIF under `data.reports`; `--report-format` selects individual formats.
The [CI gate](docs/CI-GATE.md) runs fresh analysis with explicit native configuration
and Git provenance. [Report context](docs/REPORT-CONTEXT.md) keeps candidate
consumer/test relationships and production impact explicitly unknown.

See [native setup](docs/NATIVE-SETUP.md) and [CLI behavior](docs/CLI.md). Incomplete output and empty findings do not prove a clean scan. Lifecycle attribution may remain UNKNOWN despite verified source. Stored-report, explain and case-prompt CLI backends remain unavailable. Use `python -B -m devsift` for strict no-bytecode execution from a cold checkout.

## Contents

- `skills/devsift/`: consumer skill instructions.
- `devsift/`: Python CLI, scan coordination, evidence, policy and adapters.
- `native/`: language analyzers.
- `policy/`, `schemas/`: executable defaults and validation contracts.
- `tests/`, `tools/build_native.py`, `.github/`: runtime verification and build tools.
- `docs/`: runtime usage and implementation documentation.

Specifications, historical references, task plans, the live ledger and development orchestration belong only to [devsift-specs](https://github.com/orchex006/devsift-specs). See [development](DEVELOPMENT.md). No package release is implied; the owner has not selected a license.
