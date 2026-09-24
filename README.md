> **License:** Source-visible, not open source. Original material is proprietary. Commercial use, redistribution, hosted-service use, and commercial derivative products require written permission. See [LICENSE](LICENSE) and [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md). Separately identified third-party components retain their own licenses.

# Project Runner

Public-safe orchestration kernel for Patrick's multi-repository project ecosystem.

> Redundant? No. It's just an extra redundancy.

Project Runner answers: what exists, what changed, what depends on the change, what work is justified and authorized, what can execute now, and what evidence demonstrates completion.

## Current state: M6 bounded execution fabric

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
- recursive work identity, parent linkage, exact ancestry, budget scope, lifecycle status, and generation survive restart in a digest-verified SQLite record;
- recursive child admission is one SQLite transaction: parent-budget CAS, child-budget creation, and child-work/ancestry persistence either all commit or all roll back;
- ordinary child budget/work initialization is rejected so callers cannot bypass the atomic admission path;
- each durable work record integrity-binds its effective capability ceiling; child admission derives the parent ceiling from durable state, so a restarted caller cannot widen inherited capabilities;
- pre-ceiling legacy recursive records are accepted only after their legacy integrity digest verifies, then migrate conservatively to their recorded required-capability set;
- durable dispatch admission commits budget reservation, lease claim/fencing token, and WorkUnit `CLAIMED` state in one SQLite transaction **before** backend execution;
- a crash after durable dispatch admission cannot restore the reserved active/backend-job quota or forget the owning lease/work state;
- retry/unknown redispatch consumes retry quota while reclaiming with a higher fence;
- the atomic boundary reconstructs the durable parent and re-runs decomposition/capability narrowing rather than trusting a caller-supplied `ChildAdmission`;
- lease-bound nonterminal work states (`CLAIMED`, `RUNNING`, `VERIFYING`, `FAILED_RETRYABLE`, `OUTCOME_UNKNOWN`) require the exact current holder/fencing token and an unexpired lease at transition time;
- retryable/unknown outcomes therefore cannot be asserted by a non-owner; after expiry, a reclaimed higher fence may resume them through the allowed lifecycle;
- durable lifecycle follows an explicit forward state machine; ownership never authorizes forward skips or backward active transitions;
- terminal finalization is atomic: verification proposes the terminal outcome without mutating the lease, then one SQLite transaction finalizes the exact lease fence and WorkUnit terminal status together;
- direct terminal status CAS is rejected, eliminating the crash window that could strand `VERIFYING` beside a separately completed lease;
- durable work status cannot roll terminal states back or reset active work to `PENDING`;
- stale generations/fences fail closed across both the lease table and the durable WorkUnit lifecycle;
- CI exercises the actual GitHub backend against the workflow repository in read-only mode;
- M4 post-work currentness and independent completion-evidence rules remain in force.

The live CI route still has only `contents: read`; it proves exact-head GitHub connectivity and the read-only HC Brain → Transcendence M6 path without manufacturing downstream mutation authority.

## Quick start

    python -m pip install -e '.[dev]'
    project-runner validate
    project-runner inventory
    project-runner dispatch-report --before tests/fixtures/observations-before.yaml --after tests/fixtures/observations-after.yaml --dependencies tests/fixtures/m3-dependencies.yaml
    project-runner github-read-smoke --repository thebrazenbeard/project-runner --ref main
    python -m pytest -q

## Private portfolio registry

The committed `registry/projects.yaml` is a public-safe seed. It may name repositories that were already part of Project Runner's historical public baseline, but it must not expand the public repository with additional private project identifiers merely because those projects are relevant to orchestration.

For a complete private portfolio, supply a **complete replacement registry** from outside this checkout and pin the exact expected bytes:

    PROJECT_RUNNER_PROJECT_REGISTRY=/absolute/private/path/projects.yaml \
    PROJECT_RUNNER_PROJECT_REGISTRY_SHA256=<lowercase-sha256> \
    PROJECT_RUNNER_PRIVATE_COLLISION_KEY=<private-64-hex-key> \
    project-runner inventory

The override must be an absolute path and its exact SHA-256 must match before the registry is accepted. Project Runner does not merge a hidden/private layer into the committed seed.

Private frontier derivation requires `PROJECT_RUNNER_PRIVATE_COLLISION_KEY`, a separate stable 256-bit runtime key used only to derive opaque collision domains. The registry digest is a currentness binding, not secret key material. Keep the collision key outside public Git, logs, receipts, and workflow artifacts. Reuse the same key across restarts that must preserve private semantic/collision identity; deliberate key rotation creates a new private collision namespace.

Every external project record must explicitly declare assignment scope, review scope, family, and `scheduling_state`. `HELD` projects contribute no runnable capabilities even if capabilities are listed in the record; only `SCHEDULABLE` records may contribute to ready frontier derivation.

Detailed `evaluate-change`, `frontier-report`, and `dispatch-report` CLI output is disabled while an external registry is selected, preventing private project IDs, repository subjects, dependency IDs, or collision keys from being emitted into ordinary logs. Inventory/validation remain count-only.

`frontier-summary` is the private-safe visibility surface: it emits only total, READY, non-READY, and per-status counts. It never emits project IDs, subjects, dependency IDs, collision keys, reasons, or input paths, and external-input failures collapse to a generic structural-error message.

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

## Worker recovery

Project Runner and its dispatched workers do not require permanent ChatGPT conversations. Fresh runtimes reconstruct from durable repository/Bus/currentness/authority evidence; chat URLs and Custom GPT share links are locators or provenance only. See `docs/PROJECT_RUNNER_WORKER_RECONSTRUCTION_V1.md`.


## Portfolio corpus

Project Runner now keeps a descriptive portfolio corpus separate from its execution registry. The corpus records repository/workstream identity, family, activity and priority without granting scheduling or effect authority.

The public projection is `portfolio/corpus.public.json`; the contract and privacy model are documented in `portfolio/README.md` and `docs/PROJECT_RUNNER_PORTFOLIO_CORPUS_V1.md`.

The 2026-09-24 V1 cut binds a 66-repository estate (48 public / 18 private) and 15 known non-repository workstreams (2 public / 13 private). Private identifiers are not published; the public projection carries count/digest commitments instead.
