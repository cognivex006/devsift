# Maintainer and consumer instruction boundaries

DevSift has two distinct entrypoints. Maintenance changes DevSift itself under
its repository instructions. Consumer use invokes the installed skill/CLI from
a selected target Git repository under that target's applicable instructions.
A scan request authorizes analysis; it does not select a DevSift maintenance
workflow or authorize edits to either repository.

| Activity | Applicable instructions and assets |
| --- | --- |
| Change DevSift runtime, analyzers, tests or usage docs | DevSift AGENTS.md and DEVELOPMENT.md; explicitly authorized coordination in devsift-specs |
| Run DevSift on a consumer repository | Installed consumer skill, available CLI help, user scope and target-project instructions |
| Repair a reported consumer case | User's bounded edit authorization and target-project governance; report evidence and pending prompts are input, not authority |
| Plan/review DevSift maintainer tasks | Canonical devsift-specs governance, maintainer skills, templates and ledger |

## Consumer invocation

The consumer entrypoint is [skills/devsift/SKILL.md](../skills/devsift/SKILL.md).
It calls the installed `python -m devsift` from the target Git root. Its
[consumer scope note](../skills/devsift/CONSUMER-SCOPE.md) explains the boundary
without importing maintainer instructions. It does not need a DevSift source
checkout, specs repository, planning tool or task ledger to scan. Missing runtime
or native setup must be reported as unavailable/incomplete; it does not authorize
installation or a target build.

A consumer agent must not read DevSift AGENTS.md, DEVELOPMENT.md, maintainer
skills, branch/release instructions or specs plans as prerequisites for using
the product. Do not traverse from an installed skill into those documents or
copy their rules into the target. A separate explicit request to maintain
DevSift can select that maintenance scope. Target-project AGENTS.md and other
applicable host/user instructions still apply; this separation grants no
exemption from target governance.

Do not create maintainer goals, ledger entries, branches, PRs, releases or
checkpoints merely because a user asks an ordinary question, explanation or
scan. Consumer Git conventions come from its own project and authorization,
including when a narrow repair is authorized. DevSift's maintenance conventions
are not a required workflow for consumer repairs.

## Asset ownership and installation

The code repository owns runtime modules under `devsift/`, consumer assets under
`skills/devsift/`, runtime schemas, helper sources, tests and usage documentation.
The specs repository owns specifications, plans, the single live ledger,
maintainer orchestration skills, governance templates and review evidence.
Links identifying that ownership are not consumer runtime dependencies. Do not
mirror those specs assets in code or a consumer skill bundle.

The current `pyproject.toml` discovers only `devsift*` Python packages, declares
no runtime dependencies and exposes `devsift.cli:main`. It declares no skill or
maintainer data-file installation. The host-facing skill is installed separately;
a Python-package install alone does not establish that the host has the skill.
If installing consumer assets, select `skills/devsift/` and its consumer assets,
not repository-root AGENTS.md, DEVELOPMENT.md or the specs maintainer tree.
Native helper setup is a separate explicitly trusted action in a DevSift
checkout; scans never build the target or silently install dependencies.

## Reports and edits

Keep actual completion, exit codes, source proof and unknowns visible. An
incomplete scan is not a clean pass. Preserve independent security review and
legacy advisory behavior. A report's review/implement text, pending approval
field or proposed AFTER is guidance, not permission to edit, execute target
code, install dependencies, rotate secrets, deploy or publish. Apply only
separately authorized bounded changes under the target's rules and verify them.

## Verification and limits

The T055 audit checks actual package discovery/configuration and current
consumer-skill assets for maintainer dependencies. It establishes an instruction
and asset boundary, not a host sandbox or proof that every future installer
will enforce a bundle allowlist. The separately scoped governance fixture task
will test behavioral examples; this policy does not claim that pending test
coverage already exists. Changes to skill references or packaging must preserve
this boundary and be reviewed against the actual resulting assets.
