from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .backends import BackendResult
from .dispatch import DispatchAttempt
from .leases import LeaseStore
from .models import ExactSubject
from .work_units import WorkUnit, WorkUnitStatus


@dataclass(frozen=True)
class VerificationOutcome:
    work: WorkUnit
    status: WorkUnitStatus
    reason: str


SubjectReader = Callable[[ExactSubject], ExactSubject | None]
EvidenceVerifier = Callable[[WorkUnit, BackendResult], bool]


def verify_attempt(
    attempt: DispatchAttempt,
    *,
    lease_store: LeaseStore,
    now: float,
    current_subject_reader: SubjectReader,
    evidence_verifier: EvidenceVerifier,
    manage_lease: bool = True,
) -> VerificationOutcome:
    if not attempt.result.succeeded:
        if manage_lease:
            lease_store.release(attempt.lease, now=now)
        if attempt.result.classification == "PRECONDITION_FAILED":
            return VerificationOutcome(
                work=attempt.work,
                status=WorkUnitStatus.SUPERSEDED,
                reason="backend precondition no longer matches exact subject",
            )
        return VerificationOutcome(
            work=attempt.work,
            status=WorkUnitStatus.FAILED_DETERMINISTIC,
            reason="backend reported failure",
        )

    for original in attempt.work.inputs:
        current = current_subject_reader(original)
        if current is None:
            return VerificationOutcome(
                work=attempt.work,
                status=WorkUnitStatus.OUTCOME_UNKNOWN,
                reason="exact current subject could not be established",
            )
        if current.identity() != original.identity():
            if manage_lease:
                lease_store.release(attempt.lease, now=now)
            return VerificationOutcome(
                work=attempt.work,
                status=WorkUnitStatus.SUPERSEDED,
                reason="exact subject moved after execution",
            )

    if not evidence_verifier(attempt.work, attempt.result):
        return VerificationOutcome(
            work=attempt.work,
            status=WorkUnitStatus.VERIFYING,
            reason="worker/backend claim requires independent completion evidence",
        )

    if manage_lease and not lease_store.complete(attempt.lease, now=now):
        return VerificationOutcome(
            work=attempt.work,
            status=WorkUnitStatus.OUTCOME_UNKNOWN,
            reason="lease/fence no longer authorizes completion",
        )

    return VerificationOutcome(
        work=attempt.work,
        status=WorkUnitStatus.COMPLETE,
        reason="exact subject current and completion evidence verified",
    )
