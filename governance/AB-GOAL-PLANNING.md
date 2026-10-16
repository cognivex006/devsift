# Reusable A/B goal planning policy (portable to any project)

This is a tool-neutral normative contract, intentionally separate from the DevSift product. Only apply when user has authorized substantial planning or durable tracked execution. An ordinary question is not planning authorization.

## Structural classifier

- Task graph is the authority. Every task has canonical ID, assigned canonical goal, inputs/outputs, dependencies to actual task IDs, acceptance evidence, repo/file/contract ownership and risk.
- Validate no missing nodes, duplicate task ownership, cycles or invented predecessor edges.
- True entry task of goal G: no direct **or transitive** predecessor inside G.
- For each entry E, calculate transitive predecessor set P(E).
- Other goal Q is a *full-goal gate on E* **iff** all required tasks of Q belong to P(E). Record partial prerequisites separately even when full gate exists via other goals.
- **B** iff every true entry path has at least one full predecessor-goal gate. **A** iff any true entry path has zero full predecessor-goal gates.
- A does not mean immediately ready; B does not imply serial. Start an entry when that entry's specific prerequisites are accepted and capacity/locks/authorization ready. NEVER union gates across entry paths.
- A/B is structural. Task status changes alter readiness but NEVER structural class without a graph change.
- Emit A and B groups, even if one is empty; do not generate filler work.

## Required fields

Each goal includes stable `G###`, derived alias `GA###` or `GB###`, measurable outcome, required/optional task IDs, class rationale, per-entry full-goal gates and partial task prereqs, timebox <=180 active minutes, repo/locks, acceptance, evidence, status and next action.

## Migration on graph changes

Keep canonical IDs. Recompute aliases, compare prior to new. If class changes, append mapping (old alias, new alias, canonical, graph before/after, dependent links) to migration register; update cards, active sessions, issue/PR references and savepoints atomically. Never rewrite old immutable evidence.

## Acceptance semantics

Task statuses are pending/claimed/running/in_review/accepted/blocked/paused/rework. Only accepted and independently reviewed work integrated into target branch unlocks downstream. File creation/plan/console green tests alone do not mean accepted. Optional work cannot be dispatched unless selected.

## Example correctness

- Q task E depends on T001 out of P={T001,T002} => A; E ready when T001 accepted, not after T002.
- E depends on both T001,T002 of P => B.
- Two entries X1 depends on entire P, X2 entire Q => B; X1 may run when P accepted independently from Q.
- One partial entry, one full-goal entry => A; each entry independently gated.
