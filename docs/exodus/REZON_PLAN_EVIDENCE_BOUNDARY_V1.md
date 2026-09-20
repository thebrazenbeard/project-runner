# Rezon PLAN Evidence Observation Boundary V1

Status: **SOURCE EXPERIMENT / RETURN PATH ONLY / NOT A REGISTERED BACKEND**

## Exact subjects

Rezon:
- PR #79 / R51
- `8289914ec500a1392b10fe1a3774dee166e73b40`
- `src/rezon/interop.py` blob
  `e365fd637904d4402891839ab1e187e50694e96b`

Project Runner:
- PR #22
- `bee7e720ba923ef38ce87fca4c9c2560163a9360`

Rezon's current R51 documentation head has no attached hosted workflow run at
fresh readback. Its local/full/Benchmark evidence is preserved, but this
experiment does not relabel it hosted-qualified.

## Boundary under test

Rezon already defines the desired architecture:

- Rezon owns inner reasoning, Episode state, trace/provenance semantics, and its
  canonical producer identities;
- Project Runner owns durable outer work identity, currentness, leases/fences,
  target authority, external mutation/readback, and final completion.

R49-R51 provide deterministic JSON-safe `rezon.run-evidence.v1`.

This Project Runner experiment tests only whether that evidence can cross the
boundary without semantic or authority promotion.

## What the adapter validates

`runner.rezon_evidence.validate_rezon_plan_evidence()` independently checks
outer transport/structural properties that do not require importing Rezon:

- exact V1 field shape;
- deterministic top-level evidence digest;
- PLAN-only effect state;
- no accepted/rejected claim disposition;
- no claim-disposition completeness assertion;
- receipt execution IDs equal execution records in order;
- receipt source versions equal ordered first-seen trace source versions;
- trace failures are covered by receipt failure summary;
- receipt output/producer bindings equal the corresponding execution fields;
- task-envelope digest is consistent across receipt/executions.

It intentionally does **not** recompute Rezon's canonical producer identity
algorithm or decide whether Rezon's epistemic reasoning is true.

## Observation result

Successful validation returns `RezonPlanEvidenceObservation`.

The observation explicitly says:

- structurally consistent: yes;
- object origin authenticated: no;
- inner semantics independently verified: no;
- completion eligible: no;
- authority eligible: no;
- effect state: PLAN.

The module does not import Project Runner backend or completion types and is not
registered as a backend.

## Why no BackendResult yet

Project Runner's generic verification pipeline can complete successful backend
results when a trusted independent evidence verifier returns true.

Feeding Rezon PLAN evidence into that path before there is a separately
qualified outer execution adapter would create an avoidable promotion hazard.

The first experiment therefore stops at evidence observation.

Only after this boundary is qualified should a later experiment consider a
side-effect-free Rezon execution backend—and even then Rezon evidence must remain
worker/backend evidence rather than completion truth.

## Claim ceiling

A PASS can establish:

`REZON_PLAN_EVIDENCE_CAN_CROSS_TO_PROJECT_RUNNER_WITHOUT_AUTHORITY_PROMOTION`.

It cannot establish:

- actual Rezon invocation by Project Runner;
- Project Runner completion;
- Rezon semantic truth;
- object-origin authentication/signature;
- lease/fence validity;
- target authority;
- external effect;
- backend registration;
- deployment or adoption.
