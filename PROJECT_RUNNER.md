# Project Runner Operating Contract

This document states the operational invariants for the repository. It does not grant authority over downstream projects.

## Public-safe repository

Everything committed here must be safe for public disclosure. Do not commit credentials, private source payloads, private relational or autobiographical material, confidential mechanisms, or private project contents. Private projects may be represented only by the minimum public-safe metadata needed for orchestration.

## Evidence and authority

An observation, registry entry, workflow result, review, frontier, priority decision, work unit, backend result, lease, or run receipt is evidence or coordination state. It is not authority by itself. Connector permissions likewise do not silently become governance authority.

Downstream actions require target-specific capability and currentness checks. Project Runner may say work appears useful while still classifying the frontier as WAITING_AUTHORITY.

## Worker lifecycle

Workers move through evidence-backed states:

REGISTERED -> DISCOVERED -> PROFILED -> CONNECTED -> EXECUTABLE

UNAVAILABLE is a separate current-state classification for a previously expected route.

A stable locator is sufficient only for REGISTERED. A worker is EXECUTABLE only after an end-to-end route is actually demonstrated. Invocation routes are verified independently.

## M4 recursive-dispatcher ceiling

M4 may load/derive M2-M3 state and convert READY frontiers into bounded local/mock work units.

### Capability inheritance

A child work unit receives only the intersection of capabilities available to its parent and capabilities permitted by the target. Delegation may narrow capability. It may never expand it.

### Budget lineage

Recursive work consumes an existing lineage budget. Child work cannot reset recursion depth, child-count, active-work, retry, or backend-job ceilings. Budget exhaustion terminates or defers work rather than creating new quota.

### Semantic identity and leases

Equivalent work is identified from semantic inputs rather than work IDs or scheduling order. Execution claims are atomic at the lease-store boundary. The M4 in-memory store is the reference implementation; distributed implementations must provide equivalent atomic claim/reclaim semantics.

Every lease carries a monotonic fencing token. When an expired lease is reclaimed, the new fence is higher. A stale worker holding an older fence may not complete or release the reclaimed work.

### Recursive guards

A child must be semantically distinct from every work unit in its ancestry. Self-cycles and longer ancestry cycles fail closed. A child depth must advance exactly one level and remain within inherited budget.

### Collision domains

Collision keys describe mutable targets. Shared read-only evidence does not by itself serialize independent consumers. Only one representative of an overlapping collision component is admitted in a dispatch batch. Unrelated READY groups remain independently executable.

### Completion verification

Backend/worker success is a claim, not completion evidence. After execution, Project Runner rechecks every declared exact input subject.

- unchanged exact subject + independent completion evidence + valid current fence -> COMPLETE;
- exact subject moved -> SUPERSEDED;
- currentness cannot be established or completion fence is lost -> OUTCOME_UNKNOWN;
- backend succeeded but independent completion evidence is absent -> VERIFYING.

A stale result must never become COMPLETE.

### M4 effect boundary

M4's backend is deterministic and side-effect-free. M4 does not mutate downstream repositories, create downstream credentials, invoke registered Custom GPTs, dispatch GitHub Actions as workers, merge/deploy downstream work, or perform provider/runtime mutation. Those belong to later milestones and remain governed by target-specific authority.

The twelve Custom GPT records remain locator registrations. Their route states stay UNVERIFIED until an end-to-end connection is demonstrated.
