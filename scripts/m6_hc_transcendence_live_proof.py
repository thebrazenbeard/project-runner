from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile

from runner.budgets import BudgetEnvelope
from runner.dispatch import dispatch_ready
from runner.frontier import derive_frontiers
from runner.github_backend import (
    GitHubBackend,
    GitHubOperation,
    GitHubRestTransport,
    TargetAuthorityGrant,
)
from runner.m6_github import (
    GitHubCurrentSubjectReader,
    GitHubReadInspectionBackend,
    frontier_to_github_inspection_work,
)
from runner.models import ExactSubject, FrontierStatus
from runner.persistent_state import SqliteBudgetStore, SqliteLeaseStore
from runner.recursive_state import SqliteRecursiveWorkStore
from runner.propagate import derive_invalidations
from runner.registry import load_dependencies, load_observations, load_project_snapshot
from runner.verify import verify_attempt
from runner.work_units import WorkUnitStatus, work_unit_fingerprint


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SUBSTANTIVE = FIXTURES / "m6-hc-substantive.yaml"
CURRENT = FIXTURES / "m6-hc-current.yaml"
DEPENDENCIES = FIXTURES / "m6-hc-transcendence-dependencies.yaml"

TRANSCENDENCE_SUBJECT = ExactSubject(
    repository="thebrazenbeard/transcendence",
    ref="architecture/consciousness-backup-v1",
    commit="ca3965c5788cd1bbb52fc527e47e3bcd5eca6e4a",
)


def _budget() -> BudgetEnvelope:
    return BudgetEnvelope(
        lineage_id="m6-hc-transcendence-live-proof",
        max_depth=1,
        depth=0,
        remaining_children=0,
        remaining_active=1,
        remaining_retries=0,
        remaining_backend_jobs=1,
    )


def _github_backend(token: str | None) -> GitHubBackend:
    return GitHubBackend(
        transport=GitHubRestTransport(token=token),
        route_capabilities=("github.read_ref",),
        grants=(
            TargetAuthorityGrant(
                repository="thebrazenbeard/hc-brain",
                operations=(GitHubOperation.READ_REF,),
                ref_prefixes=("main",),
            ),
            TargetAuthorityGrant(
                repository="thebrazenbeard/transcendence",
                operations=(GitHubOperation.READ_REF,),
                ref_prefixes=("architecture/consciousness-backup-v1",),
            ),
        ),
    )


def main() -> int:
    previous = load_observations(SUBSTANTIVE)
    current = load_observations(CURRENT)
    dependencies = load_dependencies(DEPENDENCIES)
    registry_snapshot = load_project_snapshot(ROOT / "registry" / "projects.yaml")
    invalidations = derive_invalidations(previous, current, dependencies)
    frontiers = derive_frontiers(
        invalidations,
        capability_lookup={"transcendence": {"analyze"}},
    )
    if len(frontiers) != 1 or frontiers[0].status is not FrontierStatus.READY:
        raise RuntimeError("expected exactly one ready HC to Transcendence frontier")

    token = os.environ.get("PROJECT_RUNNER_GITHUB_TOKEN")
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "m6-live.sqlite3"
        budget_store = SqliteBudgetStore(db)
        generation = budget_store.put_initial(_budget())
        persisted_budget, observed_generation = budget_store.get(
            "m6-hc-transcendence-live-proof"
        )
        if observed_generation != generation:
            raise RuntimeError("budget generation changed before dispatch")

        lease_store = SqliteLeaseStore(db)
        recursive_store = SqliteRecursiveWorkStore(db)
        execution_backend = GitHubReadInspectionBackend(_github_backend(token))

        def durable_work_factory(frontier, depth):
            work = frontier_to_github_inspection_work(
                frontier,
                TRANSCENDENCE_SUBJECT,
                depth,
                registry_digest=registry_snapshot.sha256,
            )
            fingerprint = work_unit_fingerprint(work)
            recursive_store.put_initial(
                work=work,
                lineage_id=persisted_budget.lineage_id,
                budget_scope_id=persisted_budget.scope_id,
                parent_fingerprint=None,
                ancestry_fingerprints={fingerprint},
                effective_capabilities={"read", "analyze"},
            )
            return work

        batch = dispatch_ready(
            frontiers,
            lease_store=lease_store,
            backend=execution_backend,
            budget=persisted_budget,
            holder="github-actions-m6-live-proof",
            now=0.0,
            lease_ttl=60.0,
            work_factory=durable_work_factory,
        )
        if len(batch.attempts) != 1:
            raise RuntimeError("expected exactly one dispatched live inspection")

        new_generation = budget_store.compare_and_swap(
            batch.remaining_budget,
            expected_generation=generation,
        )
        attempt = batch.attempts[0]
        independent_reader = GitHubCurrentSubjectReader(_github_backend(token))
        outcome = verify_attempt(
            attempt,
            lease_store=lease_store,
            now=1.0,
            current_subject_reader=independent_reader.read,
            evidence_verifier=lambda work, result: (
                result.succeeded
                and result.outputs == ("READ_REF_OK", "READ_REF_OK")
                and result.evidence
                == (
                    "m6:github-read-inspection",
                    "github:readback-verified",
                    "subjects=2",
                )
            ),
        )
        durable_work = recursive_store.compare_and_swap_status(
            lineage_id=persisted_budget.lineage_id,
            work_fingerprint_value=work_unit_fingerprint(attempt.work),
            expected_generation=1,
            status=outcome.status,
        )
        if outcome.status is not WorkUnitStatus.COMPLETE:
            raise RuntimeError(
                "live inspection did not complete: "
                f"{outcome.status.value} "
                f"(backend={attempt.result.classification})"
            )
        if durable_work.generation != 2:
            raise RuntimeError("durable recursive work generation did not advance")

        budget_store.close()
        lease_store.close()
        recursive_store.close()

        reopened_budget = SqliteBudgetStore(db)
        stored_budget, stored_generation = reopened_budget.get(
            "m6-hc-transcendence-live-proof"
        )
        if stored_generation != new_generation:
            raise RuntimeError("durable budget generation did not survive reopen")
        if stored_budget.remaining_active != 0:
            raise RuntimeError("durable active budget was not consumed")
        if stored_budget.remaining_backend_jobs != 0:
            raise RuntimeError("durable backend budget was not consumed")
        reopened_budget.close()

        reopened_recursive = SqliteRecursiveWorkStore(db)
        resumed_work = reopened_recursive.get(
            persisted_budget.lineage_id,
            work_unit_fingerprint(attempt.work),
        )
        if resumed_work is None:
            raise RuntimeError("durable recursive work disappeared after restart")
        if resumed_work.work != replace(
            attempt.work,
            status=WorkUnitStatus.COMPLETE,
        ):
            raise RuntimeError("durable recursive work changed across restart")
        if resumed_work.work.status is not WorkUnitStatus.COMPLETE:
            raise RuntimeError("durable recursive work status did not survive restart")
        if resumed_work.ancestry_fingerprints != {
            work_unit_fingerprint(attempt.work)
        }:
            raise RuntimeError("durable recursive root ancestry changed across restart")
        recursive_generation = resumed_work.generation
        reopened_recursive.close()

    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "reaction": frontiers[0].work_type,
                "provider_head": frontiers[0].subject.commit,
                "consumer_head": TRANSCENDENCE_SUBJECT.commit,
                "budget_generation": new_generation,
                "recursive_work_generation": recursive_generation,
                "recursive_work_status": WorkUnitStatus.COMPLETE.value,
                "fencing_token": attempt.lease.fencing_token,
                "route": "github.read_ref",
                "project_registry_sha256": registry_snapshot.sha256,
                "subjects_verified": 2,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
