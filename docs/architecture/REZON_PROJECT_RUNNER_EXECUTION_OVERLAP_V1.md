# Rezon / Project Runner Execution-Substrate Overlap — Audit Candidate V1

Status: `IDEA_OR_FUTURE_FRONTIER` / architecture hypothesis only.  
Date: 2026-09-19.  
Base observation: Project Runner `main@bc05812b560b4fcde3a362e72fba04c626cafac8`.  
Fresh candidate observations at capture:
- Project Runner PR #2 `work/public-safe-portfolio-registry-v2@ef1f665ab16ef3a3426cec3f70900bdc6a98e420`;
- Rezon PR #71 `work/rezon-kernel-v0-r49-project-runner-evidence-export@8ed6bfff2703f57b002daf30df2260f02c0c2183`;
- Rezon PR #74 `work/rezon-kernel-v0-r50-receipt-source-version-binding@91253aaad94cc3a656321186935a89791f8a08ce`;
- Rezon R51 work is active and moving; refresh exact current head before relying on it.

This note does not authorize code movement, merge, deployment, runtime integration, or a shared-kernel cut.

## Why this audit exists

Project Runner and Rezon have independently developed overlapping execution mechanics while retaining materially different upper-level semantics.

Project Runner currently owns portfolio/work orchestration concerns such as durable work identity, dependency/currentness logic, deduplication, collision handling, budgets, leases/fencing, persistent execution state, retries/reconciliation, dispatch, backend execution, and completion verification.

Rezon owns reasoning semantics such as TaskEnvelope meaning, typed propositions/evidence, reasoning-node topology, executor independence, evidence isolation, Episode mutation rules, opposition/falsification, integration, subject/identity state, and reasoning-specific receipts.

Rezon's roadmap also names resource-aware distributed scheduling requirements that materially overlap mechanisms Project Runner has already implemented. Rezon R49 adds a deliberately side-effect-free `rezon.run-evidence.v1` export specifically for outer orchestrators such as Project Runner. That is evidence of an intended composition boundary, not proof that either repository should absorb the other.

## Hypothesis to test

The strongest candidate architecture is not "copy Project Runner into Rezon" and not "make Rezon a Project Runner feature."

A possible architecture is a small generic execution substrate consumed by both systems, with semantic responsibility remaining above it.

Candidate generic concerns:

- durable work/execution identity;
- dependency-aware scheduling primitives;
- semantic deduplication hooks;
- collision/fencing primitives;
- scoped resource budgets;
- leases and monotonic fencing;
- persistent attempt/work state;
- retry and ambiguous-completion reconciliation;
- crash/restart recovery;
- worker dispatch/backend abstraction;
- resource accounting;
- exact completion/readback primitives.

Likely Rezon-specific concerns that should remain above any generic layer:

- TaskEnvelope semantics;
- Proposition/Evidence typing;
- Episode semantics and canonical mutation;
- reasoning-node semantics;
- strong-independence and evidence-isolation rules;
- reasoning-source provenance;
- opposition/falsification semantics;
- reasoning integration;
- subject/identity reasoning state;
- admission of reasoning outputs as canonical reasoning state.

Likely Project Runner-specific concerns that should remain above any generic layer:

- portfolio/project registry;
- project scheduling posture;
- cross-project dependency/frontier propagation;
- target repository grants;
- GitHub-specific operations and readback;
- portfolio privacy projection;
- project-level authority/currentness semantics.

## Required overlap audit

Before extracting or copying implementation, classify each materially similar mechanism as exactly one of:

- `REUSE_AS_IS`
- `GENERALIZE_AND_SHARE`
- `KEEP_PROJECT_SPECIFIC`
- `SEMANTICALLY_SIMILAR_BUT_MUST_REMAIN_SEPARATE`
- `DUPLICATE_IMPLEMENTATION_TO_ELIMINATE`
- `NEEDS_MORE_EVIDENCE`

The audit should compare exact code and contracts, not names.

At minimum compare:

- work/execution identity;
- scheduling and dependency graphs;
- budgets;
- leases/fencing;
- retry semantics;
- crash/restart recovery;
- persistence;
- ambiguous outcome reconciliation;
- currentness;
- result/completion verification;
- receipts/evidence export;
- worker independence;
- evidence isolation;
- authority boundaries;
- mutable-state protection;
- provider/backend routing.

## Countervoice / hostile review

A shared scheduler is too broad a conclusion.

The main risk is building a generic "god kernel" that silently imports Rezon reasoning validity into Project Runner or Project Runner portfolio authority into Rezon. Shared implementation is justified only where both systems need the same mechanism with the same invariant.

The strongest version of the idea therefore starts with a boundary audit, not a refactor.

Rezon R49 is particularly useful because its evidence export is intentionally narrower than Project Runner completion: it exports structural reasoning evidence while explicitly leaving outer currentness, authority, fencing, and completion verification to the orchestrator. Preserve that separation unless exact evidence proves a better one.

## Dedicated compute implication

A high-core-count, high-memory execution node makes this overlap operationally important rather than aesthetic. Real concurrent workers create failure modes around lease ownership, stale results, resource budgets, restart recovery, mutable collisions, and partial completion. The durable execution mechanics should not be reimplemented independently without a reason.

Hardware availability is not itself a reason to centralize architecture.

## Acceptance condition for future integration work

Do not extract a shared package until the audit demonstrates at least one mechanism whose:

1. semantics match in both consumers;
2. failure behavior matches;
3. authority/currentness meaning is not broadened;
4. persistence/versioning boundary is explicit;
5. independent tests can prove each consumer retains its project-specific invariants.

Until then, this remains a future architecture frontier, not an accepted shared-kernel decision.
