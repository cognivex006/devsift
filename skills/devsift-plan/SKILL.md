---
name: devsift-plan
description: Build a bounded, evidence-backed development task DAG and classify each goal into GA/GB by entry-path transitive closure; read-only planning until explicitly authorized.
---

## Trigger

Explicit product planning, implementation roadmap, work breakdown, goal/task scheduling or reprioritization for DevSift. Ordinary question or use of a consumer lint package does not create task artifacts.

1. Read target AGENTS chain and DEVELOPMENT.md only if working on source repository, detect authorized scope, read accepted evidence/ledger/graph and current Git state.
2. Decompose acceptance-first T### tasks with concrete owner, output, actual prerequisites and tests. Avoid dependencies from numeric order, language or visual convenience.
3. Validate missing task/goal references, multiple ownership, cycles and transitive prerequisite sets. True entries have no direct/transitive predecessor task inside their goal.
4. For every entry path, a predecessor goal is a full gate iff all of that predecessor's tasks are in the entry's transitive prerequisite set. Class B only when all entries have at least one full gate. Otherwise A; keep gates per path, not a union.
5. Preserve canonical IDs and proof. Class change requires execution ID mapping and migration updates; runtime statuses must never change structural class by themselves.
6. Produce explicit A and B groups (state Empty if empty), goal cards with canonical/execution ID, outcome, task IDs, class reason, per-path gate/prereqs, repo/locks, acceptance/status/evidence/next, ≤180-minute timebox including review/checkpoint.
7. Run `python tools/planctl.py validate`, `python -m unittest discover -s tests -v`. Do not edit product source, issue PR or spawn subagents merely for planning.
