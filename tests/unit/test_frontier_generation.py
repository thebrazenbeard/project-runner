from runner.frontier import derive_frontiers
from runner.models import DependencyReaction, ExactSubject, FrontierStatus
from runner.propagate import Invalidation


def _invalidation(reaction=DependencyReaction.REREVIEW):
    return Invalidation(
        dependency_id="dep-1",
        provider="vera-control-plane",
        consumer="vera",
        changed_subject=ExactSubject(
            repository="thebrazenbeard/vera-control-plane",
            ref="main",
            commit="abc123",
            path="control/current.yaml",
        ),
        reaction=reaction,
    )


def test_invalidation_becomes_matching_frontier():
    frontiers = derive_frontiers(
        (_invalidation(),),
        capability_lookup={"vera": {"read", "analyze"}},
    )
    assert len(frontiers) == 1
    assert frontiers[0].work_type == "REREVIEW"
    assert frontiers[0].status is FrontierStatus.READY
    assert frontiers[0].required_capabilities == ("analyze",)


def test_missing_capability_yields_waiting_authority():
    frontiers = derive_frontiers(
        (_invalidation(),),
        capability_lookup={"vera": {"read"}},
    )
    assert frontiers[0].status is FrontierStatus.WAITING_AUTHORITY


def test_block_reaction_yields_waiting_dependency():
    frontiers = derive_frontiers(
        (_invalidation(DependencyReaction.BLOCK),),
        capability_lookup={"vera": {"read", "analyze"}},
    )
    assert frontiers[0].status is FrontierStatus.WAITING_DEPENDENCY


def test_no_action_creates_no_frontier():
    frontiers = derive_frontiers(
        (_invalidation(DependencyReaction.NO_ACTION),),
        capability_lookup={"vera": {"read", "analyze"}},
    )
    assert frontiers == ()
