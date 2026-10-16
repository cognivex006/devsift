# DevSift

A code-quality skill backed by a read-only Python CLI and optional native analyzers for .NET, TypeScript, Go and SQL. The skill guides an agent to run checks and interpret source-linked findings.

## Use

Requires Python 3.12+. Install the package into a trusted Python environment (preferably a virtual environment) from the trusted checkout with `python -m pip install .`, and load [skills/devsift](skills/devsift/SKILL.md) in your agent host. Pip installs the CLI; the skill folder is installed separately in the host's skill directory.

From the target Git repository root:

```sh
python -I -B -m devsift --help
python -I -B -m devsift doctor
python -I -B -m devsift scan --changed
python -I -B -m devsift scan --all --legacy-mode recommend
```

A scan without configured native tools inventories source and returns incomplete. Actual analysis requires an explicitly trusted absolute manifest and independently trusted SHA256:

```sh
python -I -B -m devsift scan --changed --native-manifest /absolute/trusted-tools.json --native-manifest-digest <sha256>
```

Add `--security` for bounded credential and supported logging/TLS checks; see [security coverage](docs/SECURITY-ANALYSIS.md). The [CI gate](docs/CI-GATE.md) runs fresh analysis with explicit native configuration and Git provenance. [Report context](docs/REPORT-CONTEXT.md) keeps candidate consumer/test relationships and production impact explicitly unknown.

See [native setup](docs/NATIVE-SETUP.md) and [CLI behavior](docs/CLI.md). Incomplete output and empty findings do not prove a clean scan. Lifecycle attribution may remain UNKNOWN despite verified source. Scan and CI return full JSON, Markdown and SARIF in `data.reports`. Explicit `prompt --scan-input` composes one source-reproved case review or implementation proposal; operator approval never grants automatic source writes. `report --latest` and `explain` storage discovery remain unavailable.

## Contents

- `skills/devsift/`: consumer skill instructions.
- `devsift/`: Python CLI, scan coordination, evidence, policy and adapters.
- `native/`: language analyzers.
- `policy/`, `schemas/`: executable defaults and validation contracts.
- `tests/`, `tools/build_native.py`, `.github/`: runtime verification and build tools.
- `docs/`: runtime usage and implementation documentation.

Specifications, historical references, task plans, the live ledger and development orchestration belong only to [devsift-specs](https://github.com/orchex006/devsift-specs). See [development](DEVELOPMENT.md). No package release is implied; the owner has not selected a license.

See [Doctor diagnostics](docs/DOCTOR.md), [case prompts and approval](docs/CASE-PROMPTS.md), and [source-linked report context](docs/REPORT-CONTEXT.md) for the implemented workflows. Isolated `-I -B` invocations avoid consumer module shadowing and bytecode writes; use the interpreter containing the trusted installation.
