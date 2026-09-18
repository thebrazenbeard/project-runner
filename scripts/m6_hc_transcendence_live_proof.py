from __future__ import annotations

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
from runner.propagate import derive_invalidations
from runner.registry import load_dependencies, load_observations, load_project_snapshot
from runner.verify import verify_attempt
from runner.work_units import WorkUnitStatus


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SUBSTANTIVE = FIXTURES / "m6-hc-substantive.yaml"
CURRENT = FIXTURES / "m6-hc-current.yaml"
DEPENDENCIES = FIXTURES / "m6-hc-transcendence-dependencies.yaml"

TRANSCENDENCE_SUBJECT = ExactSubject(
    repository="thebrazenbeard/transcendence",
    ref="architecture/consciousness-backup-v1",
    commit="96e5cc93d5cf362342c3f0f323c4e63c66cc8784",
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
        execution_backend = GitHubReadInspectionBackend(_github_backend(token))
        batch = dispatch_ready(
            frontiers,
            lease_store=lease_store,
            backend=execution_backend,
            budget=persisted_budget,
            holder="github-actions-m6-live-proof",
            now=0.0,
            lease_ttl=60.0,
            work_factory=lambda frontier, depth: frontier_to_github_inspection_work(
                frontier,
                TRANSCENDENCE_SUBJECT,
                depth,
                registry_digest=registry_snapshot.sha256,
            ),
        )
        if len(batch.attempts) != 1:
            raise RuntimeError("expected exactly one dispatched live inspection")

        new_generation = budget_store.compare_and_swap(
            batch.remaining_budget,
            expected_generation=generation,
        )
        attempt = batch.attempts[0]
        if not attempt.result.succeeded:
            raise RuntimeError(
                f"live inspection backend failed: {attempt.result.classification}"
            )

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
        if outcome.status is not WorkUnitStatus.COMPLETE:
            raise RuntimeError(
                f"live inspection did not complete: {outcome.status.value}"
            )

        budget_store.close()
        lease_store.close()

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

    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "reaction": frontiers[0].work_type,
                "provider_head": frontiers[0].subject.commit,
                "consumer_head": TRANSCENDENCE_SUBJECT.commit,
                "budget_generation": new_generation,
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
