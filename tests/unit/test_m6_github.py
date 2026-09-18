from runner.budgets import BudgetEnvelope
from runner.dispatch import dispatch_ready
from runner.github_backend import (
    GitHubBackend,
    GitHubOperation,
    TargetAuthorityGrant,
)
from runner.leases import InMemoryLeaseStore
from runner.m6_github import (
    GitHubCurrentSubjectReader,
    GitHubReadInspectionBackend,
    frontier_to_github_inspection_work,
)
from runner.models import CostClass, ExactSubject, Frontier, FrontierStatus


HC_HEAD = "618245b54fb923c7a204892c6953ab6d1c5dac57"
TRANSCENDENCE_HEAD = "96e5cc93d5cf362342c3f0f323c4e63c66cc8784"


class FakeReadTransport:
    def __init__(self):
        self.heads = {
            ("thebrazenbeard/hc-brain", "main"): HC_HEAD,
            (
                "thebrazenbeard/transcendence",
                "architecture/consciousness-backup-v1",
            ): TRANSCENDENCE_HEAD,
        }
        self.calls = []

    def read_ref(self, repository, ref):
        self.calls.append((repository, ref))
        return self.heads[(repository, ref)]


def _frontier():
    return Frontier(
        id="frontier-hc-transcendence",
        project="transcendence",
        subject=ExactSubject(
            repository="thebrazenbeard/hc-brain",
            ref="main",
            commit=HC_HEAD,
        ),
        work_type="INSPECT",
        reason="HC reference substrate moved",
        dependencies=("hc-brain-to-transcendence-reference-inspection",),
        required_capabilities=("analyze",),
        collision_keys=("project:transcendence",),
        cost_class=CostClass.SMALL,
        priority_inputs={
            "criticality": 1,
            "dependency_depth": 1,
            "staleness": 1,
            "uncertainty": 1,
            "cost": 1,
        },
        status=FrontierStatus.READY,
    )


def _target():
    return ExactSubject(
        repository="thebrazenbeard/transcendence",
        ref="architecture/consciousness-backup-v1",
        commit=TRANSCENDENCE_HEAD,
    )


def _budget():
    return BudgetEnvelope(
        lineage_id="m6-live-read",
        max_depth=1,
        depth=0,
        remaining_children=0,
        remaining_active=1,
        remaining_retries=0,
        remaining_backend_jobs=1,
    )


def _grant(repository, ref):
    return TargetAuthorityGrant(
        repository=repository,
        operations=(GitHubOperation.READ_REF,),
        ref_prefixes=(ref,),
    )


def _backend(transport, *, include_target=True):
    grants = [
        _grant("thebrazenbeard/hc-brain", "main"),
    ]
    if include_target:
        grants.append(
            _grant(
                "thebrazenbeard/transcendence",
                "architecture/consciousness-backup-v1",
            )
        )
    return GitHubBackend(
        transport=transport,
        route_capabilities=("github.read_ref",),
        grants=tuple(grants),
    )


def test_m6_read_adapter_requires_explicit_grants_for_provider_and_target():
    transport = FakeReadTransport()
    backend = GitHubReadInspectionBackend(
        _backend(transport, include_target=False)
    )
    target = _target()
    batch = dispatch_ready(
        (_frontier(),),
        lease_store=InMemoryLeaseStore(),
        backend=backend,
        budget=_budget(),
        holder="m6-authority-test",
        now=0.0,
        lease_ttl=30.0,
        work_factory=lambda frontier, depth: frontier_to_github_inspection_work(
            frontier,
            target,
            depth,
        ),
    )

    assert len(batch.attempts) == 1
    result = batch.attempts[0].result
    assert result.succeeded is False
    assert result.classification == "AUTHORITY_DENIED"
    joined = " ".join(result.outputs + result.evidence)
    assert "transcendence" not in joined
    assert "thebrazenbeard" not in joined
    assert TRANSCENDENCE_HEAD not in joined


def test_m6_read_adapter_checks_both_exact_heads_and_redacts_result_metadata():
    transport = FakeReadTransport()
    backend = GitHubReadInspectionBackend(_backend(transport))
    target = _target()
    batch = dispatch_ready(
        (_frontier(),),
        lease_store=InMemoryLeaseStore(),
        backend=backend,
        budget=_budget(),
        holder="m6-success-test",
        now=0.0,
        lease_ttl=30.0,
        work_factory=lambda frontier, depth: frontier_to_github_inspection_work(
            frontier,
            target,
            depth,
        ),
    )

    assert len(batch.attempts) == 1
    result = batch.attempts[0].result
    assert result.succeeded is True
    assert result.outputs == ("READ_REF_OK", "READ_REF_OK")
    assert result.evidence == (
        "m6:github-read-inspection",
        "github:readback-verified",
        "subjects=2",
    )
    joined = " ".join(result.outputs + result.evidence)
    assert "hc-brain" not in joined
    assert "transcendence" not in joined
    assert HC_HEAD not in joined
    assert TRANSCENDENCE_HEAD not in joined
    assert transport.calls == [
        ("thebrazenbeard/hc-brain", "main"),
        (
            "thebrazenbeard/transcendence",
            "architecture/consciousness-backup-v1",
        ),
    ]


def test_independent_subject_reader_uses_separate_authority_gated_read():
    transport = FakeReadTransport()
    reader = GitHubCurrentSubjectReader(_backend(transport))

    observed = reader.read(_target())

    assert observed == _target()
    assert transport.calls == [
        (
            "thebrazenbeard/transcendence",
            "architecture/consciousness-backup-v1",
        )
    ]
