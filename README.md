# Project Runner

Public-safe orchestration kernel for Patrick's multi-repository project ecosystem.

> Redundant? No. It's just an extra redundancy.

Project Runner answers: what exists, what changed, what depends on the change, what work is justified and authorized, what can execute now, and what evidence demonstrates completion.

## Current state: M5 GitHub backend

M1 established typed project/worker registries. M2 added exact observations, dependency/currentness logic, and invalidation propagation. M3 added frontier generation, semantic deduplication, collision grouping, and deterministic priority. M4 added bounded recursive work units, budgets, fenced leases, mock dispatch, and exact-subject completion checks.

M5 adds the first real GitHub execution route:

- JSON-bound operation payloads are part of semantic work identity;
- GitHub REST transport supports exact ref reads, branch creation, and UTF-8 file writes;
- technical backend capability and target repository authority are independent gates;
- target grants constrain repository, operation, ref, and path scope;
- mutations require exact expected-head/blob preconditions;
- successful writes require post-write ref/file readback;
- SQLite-backed lineage budgets persist across process/workflow boundaries with generation CAS;
- SQLite-backed leases persist claim/reclaim/completion state and monotonic fencing tokens;
- stale generations/fences fail closed;
- CI exercises the actual GitHub backend against the workflow repository in read-only mode;
- M4 post-work currentness and independent completion-evidence rules remain in force.

The M5 CI route has only `contents: read`; it proves live GitHub connectivity without performing downstream mutation.

## Quick start

    python -m pip install -e '.[dev]'
    project-runner validate
    project-runner inventory
    project-runner dispatch-report --before tests/fixtures/observations-before.yaml --after tests/fixtures/observations-after.yaml --dependencies tests/fixtures/m3-dependencies.yaml
    project-runner github-read-smoke --repository thebrazenbeard/project-runner --ref main
    python -m pytest -q

## Authority model

Backend capability answers "can this route technically perform an operation?"

Target authority answers "is this operation authorized for this exact repository/ref/path?"

Both must pass. Connector/token permissions do not manufacture governance authority.

Core invariants:

- observation is not authority;
- coordination is not authorization;
- exact evidence outranks convenience pointers;
- blocked work remains visible without stalling unrelated work;
- semantic work identity ignores incidental IDs/order but includes material payload;
- child capability and budget only narrow;
- persistent budgets cannot silently reset between workflows;
- semantic claims use atomic leases and monotonic fences;
- stale workers cannot complete reclaimed work;
- mutations use expected-state checks and exact readback;
- backend success is not completion until currentness and completion evidence are independently verified;
- public repository state remains public-safe.

See `docs/superpowers/plans/2026-09-17-m5-github-backend.md`.


## Runtime / chat independence

Project Runner is an execution role, not a permanent ChatGPT identity. A temporary ChatGPT, Work, API, CLI, or subagent terminal may instantiate it, but the role must be recoverable from GitHub, Bus state, target-repository evidence, and durable checkpoints without opening the former conversation.

See `docs/PROJECT_RUNNER_PORTFOLIO_EXECUTION_ROLE_V1.md`.
