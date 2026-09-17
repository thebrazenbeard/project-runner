# Project Runner Operating Contract

This document states the operational invariants for the repository. It does not grant authority over downstream projects.

## Public-safe repository

Everything committed here must be safe for public disclosure. Do not commit credentials, private source payloads, private relational or autobiographical material, confidential mechanisms, or private project contents. Private projects may be represented only by the minimum public-safe metadata needed for orchestration.

## Evidence and authority

An observation, registry entry, workflow result, review, or run receipt is evidence. It is not authority by itself. Connector permissions likewise do not silently become governance authority.

Downstream actions require target-specific capability and currentness checks. Project Runner may say work appears useful while still classifying the frontier as `WAITING_AUTHORITY`.

## Worker lifecycle

Workers move through evidence-backed states:

`REGISTERED -> DISCOVERED -> PROFILED -> CONNECTED -> EXECUTABLE`

`UNAVAILABLE` is a separate current-state classification for a previously expected route.

A stable locator is sufficient only for `REGISTERED`. A worker is `EXECUTABLE` only after an end-to-end route is actually demonstrated. Invocation routes are verified independently.

## M2 evidence-propagation ceiling

M2 may load exact observations and dependency declarations, compare exact subjects, identify changed subjects, and derive declared consumer reactions such as `INSPECT`, `RETEST`, `REREVIEW`, or `REQUALIFY`.

Those derived reactions are evidence-backed coordination state only. M2 does not dispatch workers, mutate downstream repositories, create credentials, expand capabilities, merge, deploy, or convert a derived invalidation into authority.

Path-selective dependencies are matched only when the changed observation identifies a path. A broad repository/head observation does not silently claim knowledge of which path changed; provider-specific diff discovery belongs in a later observation adapter.

The twelve Custom GPT records remain locator registrations. Their route states stay `UNVERIFIED` until an end-to-end connection is demonstrated.

## Future recursive execution invariant

When recursive execution is implemented, a child work unit may inherit equal or narrower authority and budget than its parent; it may never expand either. Equivalent work must deduplicate, overlapping collision domains must serialize unless proven safe, and recursion must terminate on completion, blockage, deterministic failure, supersession, exhaustion, or configured depth/budget limits.
