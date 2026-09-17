# Project Runner

Public-safe orchestration kernel for Patrick's multi-repository project ecosystem.

> Redundant? No. It's just an extra redundancy.

Project Runner is intended to answer five questions: what exists, what changed, what depends on the change, what work is now justified and authorized, and what evidence demonstrates completion.

## Current state: M3 frontier engine candidate

M1 established the typed project/worker registry kernel. M2 added exact observations, dependency intersection, currentness comparison, and invalidation propagation. M3 adds the decision layer that turns those consequences into explicit work frontiers:

- typed frontier records and schema;
- evidence-backed frontier generation from invalidations;
- explicit `READY`, `WAITING_DEPENDENCY`, and `WAITING_AUTHORITY` separation;
- semantic SHA-256 frontier fingerprints and deduplication;
- conservative duplicate-state reconciliation so blocked work cannot become ready by accident;
- transitive collision-domain partitioning based on mutable target keys;
- deterministic, explainable priority ranking;
- `policy/scheduling.yaml` for visible priority weights;
- `project-runner frontier-report` for a deterministic end-to-end M2 -> M3 report.

M3 still does **not** dispatch workers, mutate downstream repositories, grant authority from observations, create credentials, merge/deploy downstream work, or claim that any registered Custom GPT is callable. A `READY` frontier means the declared capability check for that derived work passed; it is coordination state, not a new authority grant.

## Quick start

```bash
python -m pip install -e '.[dev]'
project-runner validate
project-runner inventory
project-runner evaluate-change \
  --before tests/fixtures/observations-before.yaml \
  --after tests/fixtures/observations-after.yaml \
  --dependencies topology/dependencies.yaml
project-runner frontier-report \
  --before tests/fixtures/observations-before.yaml \
  --after tests/fixtures/observations-after.yaml \
  --dependencies tests/fixtures/m3-dependencies.yaml
python -m pytest -q
```

## Architecture

The governing design is in `docs/superpowers/specs/2026-09-17-project-runner-design.md`. The first-class worker registry is specified by `docs/superpowers/specs/2026-09-17-worker-registry-amendment.md`.

Core rules include:

- observation is not authority;
- coordination is not authorization;
- exact evidence outranks convenience pointers;
- provider movement invalidates only matching declared consumers;
- blocked work remains visible without stalling unrelated executable work;
- priority ranking is deterministic and emits reasons;
- collision keys describe mutable targets, not shared read-only evidence;
- worker authority cannot expand through delegation;
- recursive parallelism must be budgeted, deduplicated, collision-aware, and terminating;
- public repository state must remain public-safe.
