from __future__ import annotations

import unittest

from runner.currentness import observation_locus, subject_changed
from runner.models import EvidenceClass, ExactSubject, Observation


class ObservationCurrentnessTests(unittest.TestCase):
    def make_observation(
        self,
        *,
        target: str = "node-a",
        value: str = "healthy",
        commit: str = "a" * 40,
    ) -> Observation:
        return Observation(
            target=target,
            evidence_class=EvidenceClass.AUTHORITATIVE,
            subject=ExactSubject(
                repository="owner/repo",
                ref="main",
                commit=commit,
                path="src/service.py",
            ),
            observed_value=value,
            observed_at="2026-11-05T00:00:00Z",
            observer="probe",
        )

    def test_target_change_invalidates_same_source_and_value(self) -> None:
        previous = self.make_observation(target="node-a")
        current = self.make_observation(target="node-b")
        self.assertNotEqual(observation_locus(previous), observation_locus(current))
        self.assertTrue(subject_changed(previous, current))

    def test_same_target_source_and_value_does_not_invalidate(self) -> None:
        previous = self.make_observation()
        self.assertFalse(subject_changed(previous, self.make_observation()))

    def test_first_observation_value_and_commit_changes_invalidate(self) -> None:
        previous = self.make_observation()
        self.assertTrue(subject_changed(None, previous))
        self.assertTrue(subject_changed(previous, self.make_observation(value="down")))
        self.assertTrue(subject_changed(previous, self.make_observation(commit="b" * 40)))


if __name__ == "__main__":
    unittest.main()
