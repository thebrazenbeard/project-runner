from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable, Mapping

from .durable_dispatch import SqliteDispatchAdmissionStore
from .execution_promotion import (
    ExecutionPromotionReceipt,
    _read_durable_promotion,
    _read_execution_request,
)
from .github_backend import GitHubFileState, GitHubRestTransport, GitHubTransport
from .leases import Lease


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_MUTATION_FIELDS = frozenset({"updateRefs"})
_REQUIRED_UPDATE_REFS_INPUT_FIELDS = frozenset(
    {"repositoryId", "refUpdates"}
)
_REQUIRED_REF_UPDATE_FIELDS = frozenset(
    {"name", "beforeOid", "afterOid", "force"}
)


@dataclass(frozen=True)
class GitHubSourceWriteRuntimeQualification:
    repository: str
    ref: str
    exact_head: str
    tree_sha: str
    update_refs_available: bool
    before_oid_available: bool
    after_oid_available: bool
    force_available: bool
    write_exercised: bool
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "ref": self.ref,
            "exact_head": self.exact_head,
            "tree_sha": self.tree_sha,
            "update_refs_available": self.update_refs_available,
            "before_oid_available": self.before_oid_available,
            "after_oid_available": self.after_oid_available,
            "force_available": self.force_available,
            "write_exercised": self.write_exercised,
            "status": self.status,
        }


@dataclass(frozen=True)
class GitHubSourceWriteReconciliation:
    outcome: str
    reason: str
    evidence: tuple[str, ...]
    observed_head: str
    observed_blob_sha: str | None
    work_generation: int


def qualify_github_source_write_runtime(
    *,
    repository: str,
    ref: str,
    transport: GitHubRestTransport,
) -> GitHubSourceWriteRuntimeQualification:
    """Read-only qualification of the real GitHub source-write route.

    This does not create Git objects, move refs, mutate files, or test write
    permission. It proves only that the configured route can inspect the exact
    ref/commit/tree and that the GraphQL schema exposes the fields required by
    the source-write adapter.
    """
    head = transport.read_ref(repository, ref)
    if _SHA40.fullmatch(head) is None:
        raise ValueError("runtime GitHub ref did not return an exact commit")
    tree_sha = transport.read_commit_tree(repository, head)
    if _SHA40.fullmatch(tree_sha) is None:
        raise ValueError("runtime GitHub commit did not return an exact tree")

    schema = transport.inspect_update_refs_schema()
    mutation_fields = frozenset(schema.get("mutation_fields", ()))
    update_refs_fields = frozenset(
        schema.get("update_refs_input_fields", ())
    )
    ref_update_fields = frozenset(schema.get("ref_update_fields", ()))

    update_refs_available = _REQUIRED_MUTATION_FIELDS.issubset(
        mutation_fields
    ) and _REQUIRED_UPDATE_REFS_INPUT_FIELDS.issubset(update_refs_fields)
    before_oid_available = "beforeOid" in ref_update_fields
    after_oid_available = "afterOid" in ref_update_fields
    force_available = "force" in ref_update_fields

    status = (
        "PASS"
        if (
            update_refs_available
            and before_oid_available
            and after_oid_available
            and force_available
        )
        else "FAIL"
    )
    return GitHubSourceWriteRuntimeQualification(
        repository=repository,
        ref=ref,
        exact_head=head,
        tree_sha=tree_sha,
        update_refs_available=update_refs_available,
        before_oid_available=before_oid_available,
        after_oid_available=after_oid_available,
        force_available=force_available,
        write_exercised=False,
        status=status,
    )


def _load_current_lease(
    store: SqliteDispatchAdmissionStore,
    *,
    receipt: ExecutionPromotionReceipt,
) -> Lease:
    row = store.connection.execute(
        """
        SELECT holder, fencing_token, expires_at, completed
        FROM leases
        WHERE work_fingerprint = ?
        """,
        (receipt.work_fingerprint,),
    ).fetchone()
    if row is None:
        raise ValueError("source-write reconciliation lease is missing")
    if bool(row[3]):
        raise ValueError("source-write reconciliation lease is completed")
    if int(row[1]) != receipt.fencing_token:
        raise ValueError("source-write reconciliation fence is stale")
    if str(row[0]) != receipt.holder:
        raise ValueError("source-write reconciliation holder mismatch")
    return Lease(
        work_fingerprint=receipt.work_fingerprint,
        holder=receipt.holder,
        fencing_token=receipt.fencing_token,
        expires_at=float(row[2]),
    )


def _classify_unknown_source_write(
    *,
    receipt: ExecutionPromotionReceipt,
    request_payload: Mapping[str, object],
    candidate_commit_sha: str,
    candidate_blob_sha: str,
    observed_head: str,
    observed_file: GitHubFileState | None,
) -> tuple[str, str, tuple[str, ...]]:
    expected_head = str(request_payload.get("expected_head", ""))
    expected_blob = request_payload.get("expected_blob_sha")
    expected_blob_sha = (
        str(expected_blob) if expected_blob is not None else None
    )
    intended_content = str(request_payload.get("content", ""))

    evidence = (
        f"repository={receipt.repository}",
        f"ref={receipt.ref}",
        f"expected_head={expected_head}",
        f"candidate_commit={candidate_commit_sha}",
        f"candidate_blob={candidate_blob_sha}",
        f"observed_head={observed_head}",
        (
            f"observed_blob={observed_file.sha}"
            if observed_file is not None
            else "observed_blob=<missing>"
        ),
    )

    if (
        observed_head == candidate_commit_sha
        and observed_file is not None
        and observed_file.sha == candidate_blob_sha
        and observed_file.content == intended_content
    ):
        return (
            "EFFECT_CONFIRMED",
            "candidate commit/blob/content are published at the exact ref",
            evidence,
        )

    no_effect_file_match = (
        observed_file is None
        if expected_blob_sha is None
        else (
            observed_file is not None
            and observed_file.sha == expected_blob_sha
        )
    )
    if observed_head == expected_head and no_effect_file_match:
        return (
            "NO_EFFECT_CONFIRMED",
            "ref and target blob still match the pre-write state",
            evidence,
        )

    return (
        "INDETERMINATE",
        "live GitHub state matches neither the candidate publication nor the exact pre-write state",
        evidence,
    )


def reconcile_github_source_write_outcome_unknown(
    *,
    state_db,
    lineage_id: str,
    work_fingerprint_value: str,
    fencing_token: int,
    transport: GitHubTransport,
    reconciler: str,
    clock: Callable[[], float] = time.time,
) -> GitHubSourceWriteReconciliation:
    """Read-only reconcile an already-recorded OUTCOME_UNKNOWN source write.

    The function never calls a write transport operation and never retries the
    backend. It only reads the exact ref/file and records one of the existing
    durable reconciliation outcomes.
    """
    store = SqliteDispatchAdmissionStore(state_db)
    try:
        receipt = _read_durable_promotion(
            store,
            lineage_id=lineage_id,
            work_fingerprint_value=work_fingerprint_value,
            fencing_token=fencing_token,
        )
        if receipt.effect_class != "SOURCE_WRITE":
            raise ValueError(
                "source-write reconciliation requires SOURCE_WRITE promotion"
            )

        result = store.load_result(
            lineage_id=lineage_id,
            work_fingerprint_value=work_fingerprint_value,
            fencing_token=fencing_token,
        )
        if (
            result is None
            or result.succeeded
            or result.classification != "OUTCOME_UNKNOWN"
        ):
            raise ValueError(
                "source-write reconciliation requires recorded OUTCOME_UNKNOWN"
            )
        if len(result.outputs) != 2:
            raise ValueError(
                "OUTCOME_UNKNOWN result must carry candidate commit/blob"
            )
        candidate_commit_sha, candidate_blob_sha = result.outputs
        if (
            _SHA40.fullmatch(candidate_commit_sha) is None
            or _SHA40.fullmatch(candidate_blob_sha) is None
        ):
            raise ValueError(
                "OUTCOME_UNKNOWN candidate Git object identifiers are invalid"
            )

        request_payload, request_sha256 = _read_execution_request(
            store,
            lineage_id=lineage_id,
            work_fingerprint_value=work_fingerprint_value,
            fencing_token=fencing_token,
        )
        if request_payload is None or request_sha256 is None:
            raise ValueError("source-write reconciliation request is missing")
        if receipt.execution_request_sha256 != request_sha256:
            raise ValueError(
                "source-write reconciliation request/promotion mismatch"
            )
        if request_payload.get("schema") != (
            "PROJECT_RUNNER_GITHUB_SOURCE_WRITE_V1"
        ):
            raise ValueError("unexpected source-write reconciliation request")
        if request_payload.get("repository") != receipt.repository:
            raise ValueError("source-write reconciliation repository mismatch")
        if request_payload.get("ref") != receipt.ref:
            raise ValueError("source-write reconciliation ref mismatch")

        path = str(request_payload.get("path", ""))
        if not path:
            raise ValueError("source-write reconciliation path is missing")

        observed_head = transport.read_ref(
            receipt.repository,
            receipt.ref,
        )
        observed_file = transport.read_file(
            receipt.repository,
            path,
            receipt.ref,
        )
        outcome, reason, evidence = _classify_unknown_source_write(
            receipt=receipt,
            request_payload=request_payload,
            candidate_commit_sha=candidate_commit_sha,
            candidate_blob_sha=candidate_blob_sha,
            observed_head=observed_head,
            observed_file=observed_file,
        )

        lease = _load_current_lease(store, receipt=receipt)
        work_generation = store.reconcile_admitted(
            lineage_id=lineage_id,
            work_fingerprint_value=work_fingerprint_value,
            fencing_token=fencing_token,
            expected_work_generation=receipt.promoted_work_generation,
            lease=lease,
            outcome=outcome,
            reason=reason,
            evidence=evidence,
            reconciler=reconciler,
            observed_at=float(clock()),
            allow_recorded_outcome_unknown=True,
        )
        return GitHubSourceWriteReconciliation(
            outcome=outcome,
            reason=reason,
            evidence=evidence,
            observed_head=observed_head,
            observed_blob_sha=(
                observed_file.sha if observed_file is not None else None
            ),
            work_generation=work_generation,
        )
    finally:
        store.close()
