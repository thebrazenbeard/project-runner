# Project Runner

Public-safe orchestration kernel for Patrick's multi-repository project ecosystem.

> Redundant? No. It's just an extra redundancy.

Project Runner is intended to answer five questions: what exists, what changed, what depends on the change, what work is now justified and authorized, and what evidence demonstrates completion.

## Current state: M4 recursive dispatcher candidate

M1 established the typed project/worker registry kernel. M2 added exact observations, dependency intersection, currentness comparison, and invalidation propagation. M3 added frontier generation, semantic deduplication, collision grouping, and deterministic priority ranking.

M4 adds the first bounded execution layer:

- typed work units with deterministic semantic fingerprints;
- a JSON Schema contract for work-unit exchange;
- capability inheritance by parent/target intersection only;
- lineage-scoped recursion budgets that cannot reset in child work;
- atomic reference leases with expiry and monotonic fencing tokens;
- semantic ancestry/cycle rejection and depth guards;
- a deterministic side-effect-free mock execution backend;
- READY-only, collision-aware bounded dispatch;
- exact-subject post-work currentness recheck;
- independent completion-evidence gating so backend/worker self-claims are insufficient;
- stale results become SUPERSEDED rather than COMPLETE;
- unresolved currentness/fencing becomes bounded OUTCOME_UNKNOWN;
- project-runner dispatch-report for a deterministic M2 -> M3 -> M4 mock sweep.

M4 remains deliberately local/mock. It does not provide downstream write credentials, GitHub Actions dispatch, real Custom GPT invocation, production mutation, deployment, or a distributed persistent lease store. A production/distributed lease backend must preserve M4's atomic claim and fencing semantics with its own transaction/CAS primitive.

## Quick start

    python -m pip install -e '.[dev]'
    project-runner validate
    project-runner inventory
    project-runner dispatch-report --before tests/fixtures/observations-before.yaml --after tests/fixtures/observations-after.yaml --dependencies tests/fixtures/m3-dependencies.yaml
    python -m pytest -q

## Architecture

The governing design is in docs/superpowers/specs/2026-09-17-project-runner-design.md. The first-class worker registry is specified by docs/superpowers/specs/2026-09-17-worker-registry-amendment.md. The M4 implementation plan is docs/superpowers/plans/2026-09-17-m4-recursive-dispatcher.md.

Core rules include:

- observation is not authority;
- coordination is not authorization;
- exact evidence outranks convenience pointers;
- provider movement invalidates only matching declared consumers;
- blocked work remains visible without stalling unrelated executable work;
- priority ranking is deterministic and emits reasons;
- collision keys describe mutable targets, not shared read-only evidence;
- worker authority cannot expand through delegation;
- recursive children inherit budget rather than creating it;
- semantic work claims are leased atomically and guarded by monotonic fencing tokens;
- recursive decomposition rejects ancestry cycles and stops at configured depth/budget ceilings;
- successful execution is not completion until exact currentness and completion evidence are verified;
- public repository state must remain public-safe.
