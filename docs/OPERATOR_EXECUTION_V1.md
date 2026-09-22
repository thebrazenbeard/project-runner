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

## Next frontier

After this operator path is exact-head qualified, the next useful layer is a durable portfolio currentness collector and scheduler so operators do not have to hand-supply observation snapshots. Mutation execution should remain a separate gated frontier with explicit effect authority and postcondition reconciliation.
