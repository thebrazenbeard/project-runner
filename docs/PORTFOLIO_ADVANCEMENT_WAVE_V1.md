# Portfolio Advancement Wave V2

Status: source-only currentness-gated wave / no merge / no deployment / no credential or permission changes

## Purpose

This wave turns the Portfolio Corpus into bounded work rather than a passive catalog.

The corpus answers what exists and what its current frontier is. This wave assigns each subject a lead identity, independent reviewers, an action, a review gate, and an effect ceiling.

The wave deliberately does **not** authorize protected effects. Source branches, pull requests, tests, reviews, issue/PR analysis, and non-destructive repository work are in scope. Merge, deployment, destructive cleanup, credential changes, permission changes, and claims of runtime effect require separate live authority.

## Identities

- **ONE** — lead orchestrator/integrator. Sequencing, dependency routing, cross-project composition.
- **REZON** — independent reasoning/assurance reviewer. Evidence, claim boundary, independence and replay discipline.
- **VOSS** — forensic exact-head reviewer. Contradictions, provenance, source/currentness mismatch.
- **ACHILLES** — security reviewer. Trust boundary, authorization, credentials, attack path and fail-open analysis.
- **HEPHAESTUS** — builder/architecture specialist. Implementation structure, packaging and reproducibility.
- **MASAMUNE** — debugger. Reproduction, root cause, regression and defect closure.
- **DISCOVERY** — portfolio source/registry owner. Census, overlap, capability and donor discovery.
- **ROOTS** — provenance reviewer. Origin and derivation chains.
- **DRIFTGUARD** — behavioral/regression reviewer. Drift, benchmark and holdout lineage.

These names are role identities for independent passes. They do not imply separate hidden runtimes or uninterrupted private agents.

## Whole-corpus rule

Every corpus subject receives exactly one disposition.

For the 2026-09-30 V2 cut, authenticated membership is 76 accessible repositories: 57 public and 19 private. Private membership remains count-only in public source.

Only the ten P0 repositories that were freshly re-read from live GitHub are QUEUED. Semantic state inherited from the prior 2026-09-28 corpus is HELD behind CURRENTNESS_AUDIT until exact source is refreshed. The four repositories newly present in the public corpus are exact-source classified but HELD until an execution route is separately admitted. Archived and superseded subjects remain preserve-only.

This prevents "advance the whole portfolio" from turning stale descriptive status into executable currentness or from turning repository membership into authority.

## Review independence

A lead identity cannot be its own reviewer.

Every queued subject has at least one independent reviewer. High-risk families use more than one:

- Vera/runtime work includes security and assurance review.
- Cognitive/speculative work includes forensic/claim-boundary review.
- Source-critical research includes provenance and reasoning review.
- Assurance/repair work includes security/debugging review.

## Execution ceiling

The V2 default ceiling is **SOURCE_ONLY**.

Allowed work includes:

- inspect exact source;
- create isolated branches;
- write source/tests/docs;
- open draft PRs;
- run source/CI tests;
- perform exact-head reviews;
- record deterministic blockers and next frontiers.

Not authorized by this wave:

- merge;
- deploy/install;
- credential or permission changes;
- destructive cleanup;
- provider mutations merely because source exists;
- claims that a source/build change has runtime effect.

## Public/private boundary

The committed public wave covers every public corpus subject and preserves only aggregate private counts. It intentionally does not publish an unkeyed commitment to private identifiers.

The full private wave is an external execution artifact. Exact private membership must be validated there or by a keyed private commitment mechanism; it must never be copied into this public repository.

## Advancement semantics

"Advance" means one of:

- **EXECUTE_FRONTIER** — perform the current bounded source task and verify it.
- **VERIFY_REUSE_OR_HOLD** — identify a concrete consumer and prove reuse value; otherwise do not expand.
- **RUN_MINIMUM_PROOF** — run the smallest falsifiable experiment needed to justify continued architecture.
- **REFRESH_AND_HOLD** — refresh exact currentness and only reopen work when a real defect/dependency appears.
- **PRESERVE_ONLY** — no new work; preserve lineage and recoverability.
- **REFRESH_IF_REACTIVATED** — paused work remains dormant until explicitly reactivated.
- **CURRENTNESS_AUDIT** — status is too weak to execute until exact state is reconstructed.

## Initial execution order

The wave is corpus-wide, but V2 execution is deliberately narrower than the descriptive corpus.

1. Fresh P0 source/currentness work may proceed under SOURCE_ONLY.
2. Discovery must finish the 57-public deterministic evidence refresh before its stale watch can become current.
3. Newly classified subjects remain HELD until a bounded execution route is admitted.
4. Inherited non-P0 subjects receive exact-source currentness refresh before their prior frontier can execute.
5. Archived and superseded work remains preserve-only.

Independent work may proceed in parallel when it does not share mutable source/effect boundaries.

## Exact binding

The committed public wave is bound to the exact public corpus Git blob and corpus source commit recorded in `portfolio/advancement_wave.public.json`.

A changed corpus invalidates the wave until the wave is regenerated and re-reviewed.
