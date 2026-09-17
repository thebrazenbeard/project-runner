# Project Runner Operating Contract

This document states the operational invariants for the repository. It does not grant authority over downstream projects.

## Public-safe repository

Everything committed here must be safe for public disclosure. Do not commit credentials, private source payloads, private relational or autobiographical material, confidential mechanisms, or private project contents. Private projects may be represented only by the minimum public-safe metadata needed for orchestration.

## Evidence and authority

An observation, registry entry, workflow result, review, frontier, priority decision, or run receipt is evidence or coordination state. It is not authority by itself. Connector permissions likewise do not silently become governance authority.

Downstream actions require target-specific capability and currentness checks. Project Runner may say work appears useful while still classifying the frontier as `WAITING_AUTHORITY`.

## Worker lifecycle

Workers move through evidence-backed states:

`REGISTERED -> DISCOVERED -> PROFILED -> CONNECTED -> EXECUTABLE`

`UNAVAILABLE` is a separate current-state classification for a previously expected route.

A stable locator is sufficient only for `REGISTERED`. A worker is `EXECUTABLE` only after an end-to-end route is actually demonstrated. Invocation routes are verified independently.

## M3 frontier-engine ceiling

M3 may load exact observations and dependency declarations, compare exact subjects, derive invalidations, generate frontiers, deduplicate equivalent work, group overlapping collision domains, and deterministically rank work with explicit reasons.

Frontier state is not effect authority:

- `READY` means the frontier is not currently blocked by its declared dependency state or required-capability comparison.
- `WAITING_DEPENDENCY` means the declared dependency condition blocks progress.
- `WAITING_AUTHORITY` means the required capability is absent from the current declared capability set.

A high-priority blocked frontier remains visible but must not suppress unrelated `READY` work. Numeric priority never overrides authority or dependency classification.

Collision keys describe mutable targets. Shared provider evidence is not itself a reason to serialize independent consumers. Overlapping target collision domains are grouped transitively.

M3 does not dispatch workers, mutate downstream repositories, create credentials, expand capabilities, merge, deploy, or turn a priority decision into authority.

The twelve Custom GPT records remain locator registrations. Their route states stay `UNVERIFIED` until an end-to-end connection is demonstrated.

## Future recursive execution invariant

When recursive execution is implemented, a child work unit may inherit equal or narrower authority and budget than its parent; it may never expand either. Equivalent work must deduplicate, overlapping collision domains must serialize unless proven safe, and recursion must terminate on completion, blockage, deterministic failure, supersession, exhaustion, or configured depth/budget limits.
