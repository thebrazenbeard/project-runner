# Portfolio Discovery Policy V1

Status: EXODUS_CANDIDATE
Last discovery cut: 2026-09-20

Project Runner must not rely on a hand-maintained chat list as the complete project inventory.

A fresh portfolio pass discovers repositories from the authorized GitHub account/installation and classifies them before scheduling work.

Recommended classes:

- ACTIVE_PROJECT — durable current work exists.
- ACTIVE_INFRASTRUCTURE — shared infrastructure or execution/control surface.
- ACTIVE_WORKER_HOME — durable home of a named worker/collective.
- PLACEHOLDER — repository exists but has no current runnable implementation.
- HISTORICAL_ARCHIVE — useful provenance, not current execution.
- POSSIBLE_DUPLICATE_OR_PREDECESSOR — overlapping identity/source requires reconciliation before use.
- NEEDS_CLASSIFICATION — evidence is insufficient to promote into the active portfolio.

Discovery must preserve repository-local autonomy. A newly discovered repository is not automatically coupled to Project Runner, granted write authority, or added to a shared architecture spine.

`DISCOVERABLE != COUPLED`

`COORDINATED != AUTHORIZED`

`EXECUTABLE_ROUTE != TARGET_AUTHORITY`

## Bound Discovery cut and current estate observation

The exact Discovery census consumed by `DISCOVERY_CENSUS_CONSUMER_V1` was observed on 2026-09-19 and remains intentionally frozen as drift-baseline evidence:

- repository count: **57**
- public repository count: **12**
- private repository identities/content: not mirrored into this public repository

A fresh authorized estate enumeration on 2026-09-20 now observes:

- repository count: **58**
- public repository count: **14**
- non-public repository count: **44**
- public repositories newly visible relative to the bound Discovery cut: `thebrazenbeard/god-brain` and `thebrazenbeard/voss`

This newer observation does **not** rewrite the frozen 57-repository fixture or silently promote either public repository into the runtime registry. The mismatch is the expected output of a drift/currentness mechanism: the bound census is historical exact evidence and the live inventory must be refreshed before scheduling or mutation.

- archived repositories remain historical/archive candidates rather than silently scheduled
- private repository identities/content remain outside this public repository

The previous 2026-09-17 inventory contained 53 repositories and is now historical evidence.

The 2026-09-20 pass discovered four repositories that did not exist in that older cut:

- `thebrazenbeard/mosaic`
- `thebrazenbeard/testament`
- `thebrazenbeard/driftguard`
- `thebrazenbeard/discovery`

Mosaic and Testament were already represented in the composed Exodus candidate before this refresh. DriftGuard and Discovery are public repositories with durable current project material, so they are added to the public-safe seed registry on this candidate branch.

The public seed is intentionally incomplete. It contains public-safe current projects plus legacy private identifiers already historically disclosed by Project Runner. It must not expand with additional private project identifiers merely because discovery can see them.

## Complete private inventory

The complete portfolio classification is mutable currentness state. The older 57-repository classification is historical; any current complete classification must be freshly regenerated from authorized inventory and, when used by Project Runner, selected through an external registry bound by exact SHA-256.

That private registry is a **replacement** runtime registry, not a hidden merge into public source.

Every private external project record must explicitly declare:

- assignment scope;
- review scope;
- family;
- scheduling state.

`HELD`, `ARCHIVED`, `DORMANT`, `SENSITIVE_HELD`, and `DECISION_HELD` remain observable but non-schedulable.

## Refresh rule

Repository discovery is a starting observation, not timeless truth.

Before portfolio scheduling or mutation:

1. re-enumerate authorized repositories;
2. fresh-read exact repository/ref state for the target;
3. load the exact private registry bytes when private projects are needed;
4. verify the configured SHA-256;
5. re-check scheduling state, capability, target authority, collision state, and dependencies.

A chat transcript or remembered project list never substitutes for discovery/currentness.
