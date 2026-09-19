# Portfolio Discovery Policy V1

Status: EXODUS_CANDIDATE
Date: 2026-09-19

Project Runner must not rely on a hand-maintained chat list as the complete project inventory.

A fresh portfolio pass should discover repositories from the authorized GitHub account/installation, then classify them before scheduling work.

Recommended classes:

- ACTIVE_PROJECT — durable current work exists.
- ACTIVE_INFRASTRUCTURE — shared infrastructure or execution/control surface.
- ACTIVE_WORKER_HOME — durable home of a named worker/collective.
- PLACEHOLDER — repository exists but has no current runnable implementation.
- HISTORICAL_ARCHIVE — useful provenance, not current execution.
- POSSIBLE_DUPLICATE_OR_PREDECESSOR — overlapping identity/source requires reconciliation before use.
- NEEDS_CLASSIFICATION — evidence is insufficient to promote into the active portfolio.

Discovery must preserve repository-local autonomy. A newly discovered repository is not automatically coupled to Project Runner, given write authority, or added to a shared architecture spine.

The private portfolio checkpoint stores the complete 2026-09-19 owner-repository inventory and classifications. This public repository intentionally does not mirror private repository contents.
