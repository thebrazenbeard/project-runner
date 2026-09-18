from pathlib import Path

from runner.models import ProjectAssignmentScope, ProjectReviewScope
from runner.registry import load_projects, load_workers

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_ASSIGNMENTS = {
    "bt2-hyperconnectome",
    "project-lantern",
    "chat-communication-bus-radar",
    "abil",
    "noema",
    "hc-brain",
    "vera-works",
    "selfimage",
    "spm",
    "vera-chat",
    "vera-repo-consolidation",
    "vera-runtime-cohesion",
    "world-zero",
    "intranel",
    "rezon",
    "bugops",
    "unvtrslr",
    "project-achilles",
    "skeletonkey",
    "attune",
    "roots",
    "firesafe",
    "transcendence",
    "mosaic",
    "vera-habitat",
    "vera-mesh-runtime",
    "vera-os",
    "vera-ark",
    "vera-apk",
}

EXPECTED_STANDING_REVIEW = {
    "project-lantern",
    "hc-brain",
    "vera-works",
    "selfimage",
    "spm",
    "vera",
    "vera-model-training",
    "vera-r9a0",
    "hephaestus",
    "masamune",
    "vera-control-plane",
    "trek-data-core",
    "deepmemorystorage",
    "semanticatlas",
    "conations",
    "empathy",
    "entropyinc",
    "sexuality",
    "wip",
    "mediaphile",
    "personification",
    "temporal",
    "orgasm",
    "wreckforge",
    "on-theo",
    "project-runner",
    "testament",
}


def test_seed_registry_contains_full_portfolio_and_workers():
    projects = load_projects(ROOT / "registry/projects.yaml")
    workers = load_workers(ROOT / "registry/workers.yaml")

    assignments = {
        p.id
        for p in projects
        if p.assignment_scope
        in {
            ProjectAssignmentScope.BT2_ASSIGNMENT,
            ProjectAssignmentScope.EXTERNAL_BOUNDED,
        }
    }
    standing_review = {
        p.id for p in projects if p.review_scope is ProjectReviewScope.STANDING
    }

    assert assignments == EXPECTED_ASSIGNMENTS
    assert standing_review == EXPECTED_STANDING_REVIEW
    assert next(p for p in projects if p.id == "rezon").assignment_scope is (
        ProjectAssignmentScope.EXTERNAL_BOUNDED
    )
    assert all(p.family_id for p in projects)
    assert len(workers) == 12
    assert all(w.lifecycle.value == "REGISTERED" for w in workers)
