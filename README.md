# Project Runner

Public-safe orchestration kernel for Patrick's multi-repository project ecosystem.

> Redundant? No. It's just an extra redundancy.

Project Runner is intended to answer five questions: what exists, what changed, what depends on the change, what work is now justified and authorized, and what evidence demonstrates completion.

## Current state: M1 kernel

M1 is intentionally read-only outside this repository. It provides:

- typed project and worker definitions;
- JSON Schema-backed YAML registries;
- duplicate-ID and worker-lifecycle validation;
- a five-project seed inventory;
- a twelve-worker Custom GPT inventory;
- `project-runner validate` and `project-runner inventory` commands;
- CI that tests the kernel and validates the registries.

It does **not** yet dispatch workers, mutate downstream repositories, calculate dependency invalidation, or claim that any registered Custom GPT is callable. Those arrive only after evidence-backed later milestones.

## Quick start

```bash
python -m pip install -e '.[dev]'
project-runner validate
project-runner inventory
python -m pytest -q
```

## Architecture

The governing design is in `docs/superpowers/specs/2026-09-17-project-runner-design.md`. The first-class worker registry is specified by `docs/superpowers/specs/2026-09-17-worker-registry-amendment.md`.

Core rules include:

- observation is not authority;
- coordination is not authorization;
- exact evidence outranks convenience pointers;
- worker authority cannot expand through delegation;
- recursive parallelism must be budgeted, deduplicated, collision-aware, and terminating;
- public repository state must remain public-safe.
