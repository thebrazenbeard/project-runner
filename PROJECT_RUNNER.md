# Project Runner Operating Contract

This document states Project Runner operational invariants. It does not grant authority over downstream projects.

## Public-safe repository

Everything committed here must be safe for public disclosure. Do not commit credentials, private source payloads, private relational/autobiographical material, confidential mechanisms, or private project contents.

Portfolio relevance does not imply publication authority. The committed project registry is a public-safe seed, not the complete private portfolio. Additional private project identifiers belong in a complete external registry selected explicitly with an absolute `PROJECT_RUNNER_PROJECT_REGISTRY` path and an exact `PROJECT_RUNNER_PROJECT_REGISTRY_SHA256` byte binding. The runtime treats that file as a replacement registry rather than silently merging it into public source.

External records must explicitly declare scheduling posture. `HELD` records are observable portfolio state but are not schedulable and contribute no runnable capabilities. Detailed CLI reports that would expose project IDs, repositories, dependency IDs, subjects, or collision keys are disabled while an external registry is selected.

The three private project identifiers already present on canonical M5 `main` are legacy public baseline metadata. Their prior disclosure does not authorize adding more private identifiers.

## Evidence and authority

Observations, registry entries, workflow results, reviews, frontiers, priority decisions, work units, backend results, leases, and receipts are evidence or coordination state. None grants authority by itself.

## M5 GitHub execution boundary

Project Runner now has a real GitHub REST backend, but technical execution capability and target authority are distinct.

A GitHub operation proceeds only when:

1. the backend route advertises the required technical capability;
2. an explicit target grant permits the exact repository and operation;
3. the requested ref/path is inside that grant;
4. mutable predecessor state matches the request's expected head/blob where required;
5. the effect is read back after mutation;
6. later completion verification still rechecks exact currentness and independent evidence.

Possessing a token with broad GitHub permissions does not satisfy target authority.

### Persistent lineage budget

M5 includes a SQLite lineage budget ledger with generation compare-and-swap. A workflow/process may reserve remaining lineage budget; a stale generation cannot overwrite a newer reservation. Restarting execution therefore cannot silently restore consumed child/active/retry/backend-job quota.

### Persistent leases and fencing

M5 includes a SQLite lease store. Claim/reclaim state survives process restarts. Expired work can be reclaimed with a strictly higher fencing token. Older holders cannot complete or release the reclaimed work.

### GitHub operations

The reference backend supports:

- exact ref read;
- create branch from an exact expected source head;
- create/update UTF-8 file under an authorized ref/path scope with expected-state checks and post-write readback.

Existing-file updates require the expected blob SHA; blind stale overwrite is rejected.

### CI proof

The repository CI uses the actual GitHub REST transport in read-only mode against the exact push branch and requires the observed head to equal the workflow subject SHA.

CI retains `contents: read`. The live smoke test is connectivity/currentness evidence, not downstream mutation authority.

## Preserved M4 rules

- child capabilities are intersections, never expansions;
- recursive work consumes inherited budget;
- semantic work deduplicates before claim;
- collision domains serialize conflicting mutable targets only;
- recursion/cycles terminate fail-closed;
- backend/worker success is not completion;
- stale output becomes SUPERSEDED rather than COMPLETE;
- unresolved currentness or fencing becomes bounded OUTCOME_UNKNOWN.

## Current effect ceiling

M5 does not grant standing mutation authority over another repository, deploy production systems, create credentials, invoke Custom GPTs, or infer authority from connector/token permission.

The twelve Custom GPT records remain registrations with UNVERIFIED routes until an end-to-end executable path is independently demonstrated.
