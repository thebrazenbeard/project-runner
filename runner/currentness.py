from __future__ import annotations

from .models import Observation


def subject_changed(previous: Observation | None, current: Observation) -> bool:
    if previous is None:
        return True
    return (
        previous.subject.identity() != current.subject.identity()
        or previous.observed_value != current.observed_value
    )
