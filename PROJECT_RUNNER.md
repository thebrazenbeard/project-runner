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

## M1 capability ceiling

M1 loads and validates project and worker registries. It does not dispatch work, create recursive workers, acquire downstream credentials, or mutate downstream projects.

The twelve Custom GPT records currently encode locators only. Their route states remain `UNVERIFIED` until Project Runner has evidence of a working route.

## Future recursive execution invariant

When recursive execution is implemented, a child work unit may inherit equal or narrower authority and budget than its parent; it may never expand either. Equivalent work must deduplicate, overlapping collision domains must serialize unless proven safe, and recursion must terminate on completion, blockage, deterministic failure, supersession, exhaustion, or configured depth/budget limits.
