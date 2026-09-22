# Project Runner Operator Execution V1

Status: source candidate stacked on the independently reviewed M6 canonical-baseline candidate. This document does not grant merge, deployment, or downstream mutation authority.

## Why this slice exists

Project Runner already had durable M6 work state, budgets, fenced leases, GitHub read/mutation primitives, execution journaling, currentness verification, and recovery classification. Its ordinary CLI still stopped at dispatch-report, which deliberately exercised an M4 mock backend. The system therefore had an execution engine without a general operator entry point.

Current orchestration systems converge on the same broad separation: durable workflow state is distinct from worker process lifetime, retries must not silently duplicate effects, and operator-triggered execution should be permission- and concurrency-bounded. Temporal emphasizes crash-resumable durable execution; GitHub Actions exposes explicit manual triggers, least-privilege token permissions, concurrency controls, and protected environments. Project Runner keeps its own evidence/authority model rather than importing either product's semantics.

## V1 operator contract

The command project-runner run-inspection executes exactly one already-derived READY + INSPECT frontier.

The command:

1. derives the frontier from the supplied before/after observations and dependency registry;
2. requires an exact target repository/ref/40-hex head;
3. binds the current project-registry SHA-256 into work identity;
4. creates a persistent SQLite lineage budget and root work record;
5. atomically admits execution, reserving budget and a fencing lease before backend work;
6. performs real GitHub READ_REF operations only under exact repository/ref grants;
7. journals the backend result before verification;
8. independently re-reads every exact input subject;
9. atomically finalizes terminal work + lease + verification evidence;
10. leaves interrupted attempts visible through project-runner operator-status.

The initial operator route is deliberately read-only. It does not create branches, write files, open/merge PRs, deploy, install, alter providers, or infer target authority from token capability.

## State and recovery honesty

The V1 state database is durable relative to the filesystem that stores it. SQLite is not magically cross-machine persistence. Running this command in an ephemeral CI runner without separately preserving the database does not create durable orchestration across runs.

operator-status exposes unresolved recovery classes already defined by M6. An ADMITTED attempt without a recorded result remains an ambiguous-effect state; Project Runner does not assume the backend did nothing and does not blindly re-execute it.

This slice intentionally does not auto-reconcile ambiguous effects or stale verification fences. Those require a separate bounded recovery design rather than pretending that retry is a synonym for safe.

## External/private registry behavior

The existing external registry digest and private collision-key requirements remain in force. run-inspection may operate against an explicitly selected private registry, but its success payload contains hashes/state classifications rather than repository or project identity. Detailed operator-status output is treated as a detailed report and remains disabled while an external project registry is selected.

## Research basis

- Temporal durable execution documentation: https://docs.temporal.io/
- GitHub Actions deployment controls: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments
- GitHub Actions workflow permissions and concurrency: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax

These are design references, not runtime dependencies.

## Durable portfolio currentness and scheduler V1

`project-runner portfolio-cycle` removes the requirement to hand-author before/after observation snapshots for registered dependency refs. It:

1. loads one exact project-registry snapshot and one exact dependency-registry snapshot, each digest-bound;
2. validates that every dependency provider/consumer exists and that each selector repository belongs to its declared provider;
3. requires an exact dependency ref;
4. derives exact READ_REF grants from those validated selectors and performs only read-only GitHub ref reads;
5. writes a complete currentness snapshot only after every required read succeeds;
6. treats the first cycle for an exact project-registry + dependency-registry digest pair as a baseline;
7. compares later compatible cycles to their latest durable predecessor;
8. derives invalidations, frontiers, scheduling eligibility, and priority using the existing M6 logic;
9. commits the new snapshot and all scheduler decisions in one `BEGIN IMMEDIATE` transaction with a predecessor CAS;
10. queues READY frontiers and persists blocked frontiers without executing either.

A failure during collection does not advance durable currentness. A concurrent cycle that advances the same configuration first causes the stale cycle to fail rather than overwrite or double-schedule from an obsolete predecessor.

Path-prefix dependencies are conservative in V1: currentness is collected at the exact ref head and the selector path-prefix is bound into the observation locus. A ref-head change can therefore over-invalidate a path-scoped dependency, but it cannot silently treat a changed Git commit as unchanged.

`project-runner portfolio-status` is count/digest oriented and does not dump portfolio subjects. The scheduler queue is durable evidence, not a standing execution grant.

## Fenced queue consumption and exact target resolution V1

Projects may now declare explicit `execution_targets` by work type. A target contains an exact repository and ref; its repository must already belong to the project. Target declaration is routing authority for the read-only operator bridge, not mutation authority.

Scheduler readiness now includes target availability. A schedulable/capable frontier without one declared target for its work type is persisted as `WAITING_AUTHORITY`, never `QUEUED`.

`project-runner consume-queue` consumes only READY `INSPECT` rows from the latest snapshot matching the current project-registry and dependency-registry digests. The queue bridge:

1. claims one row with a monotonic fencing token;
2. refuses collision domains already held by another live queue claim, including claims from older snapshots;
3. binds the declared consumer repository/ref and resolves its exact current head through a grant-limited READ_REF;
4. persists that target head so a reclaimed attempt cannot silently retarget;
5. derives a deterministic operator lineage from the durable snapshot/frontier identity;
6. reconstructs the exact M6 inspection work identity before any possible re-execution;
7. if matching durable operator state is already terminal, reconciles the queue from it without backend re-execution;
8. if matching durable operator state exists but is nonterminal, records `OUTCOME_UNKNOWN` and refuses blind re-execution;
9. otherwise invokes the existing durable read-only inspection operator and persists the queue outcome under the exact queue fence.

A new currentness snapshot supersedes older unclaimed queue visibility: queue consumption selects work only from the latest compatible snapshot. This prevents an old queued invalidation from running after a later snapshot has already established newer portfolio truth.

`project-runner queue-status` exposes aggregate claim states. External/private queue failures collapse to generic errors rather than echoing private registry or topology details.

The committed public-safe registry intentionally contains only the explicit execution targets already justified by public Project Runner state. Missing targets in other projects are not guessed.

## Current ceiling and next frontier

The scheduler/consumer bridge is still read-only and currently consumes `INSPECT` only. It does not manufacture targets for RETEST/REREVIEW/REQUALIFY, invoke external workers, write branches/files, open or merge PRs, deploy, install, or change providers/credentials/permissions.

The next bounded frontier is durable queue lifecycle/reconciliation tooling plus a read-only worker-routing abstraction for additional explicitly bound work types. Any mutation path remains a separate authority-gated frontier with expected-state checks and independent postcondition verification.
