# Project Runner

Public-safe orchestration kernel for Patrick's multi-repository project ecosystem.

> Redundant? No. It's just an extra redundancy.

Project Runner is intended to answer five questions: what exists, what changed, what depends on the change, what work is now justified and authorized, and what evidence demonstrates completion.

## Current state: M2 observation and dependency graph candidate

M1 established the typed project/worker registry kernel. M2 adds the read-only evidence-propagation layer:

- exact-subject observations with explicit evidence class;
- typed dependency edges and reactions;
- deterministic repository/ref/path-prefix intersection;
- exact-subject currentness comparison;
- consumer invalidation derivation;
- a small public-safe seed topology;
- `project-runner evaluate-change` for deterministic before/after fixture evaluation.

M2 still does **not** dispatch workers, mutate downstream repositories, grant authority from observations, discover live provider state by itself, or claim that any registered Custom GPT is callable. It only loads declared evidence, derives changes, and reports the dependency consequences supported by that evidence.

## Quick start

```bash
python -m pip install -e '.[dev]'
project-runner validate
project-runner inventory
project-runner evaluate-change \
  --before tests/fixtures/observations-before.yaml \
  --after tests/fixtures/observations-after.yaml \
  --dependencies topology/dependencies.yaml
python -m pytest -q
```

## Architecture

The governing design is in `docs/superpowers/specs/2026-09-17-project-runner-design.md`. The first-class worker registry is specified by `docs/superpowers/specs/2026-09-17-worker-registry-amendment.md`.

Core rules include:

- observation is not authority;
- coordination is not authorization;
- exact evidence outranks convenience pointers;
- provider movement invalidates only matching declared consumers;
- worker authority cannot expand through delegation;
- recursive parallelism must be budgeted, deduplicated, collision-aware, and terminating;
- public repository state must remain public-safe.
