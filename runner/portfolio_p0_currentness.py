from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .portfolio_corpus import load_portfolio_corpus
from .schema import validate_document


def _git_blob_sha(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def load_p0_currentness_overlay(
    overlay_path: str | Path,
    corpus_path: str | Path,
) -> dict[str, Any]:
    overlay_path = Path(overlay_path)
    corpus_path = Path(corpus_path)

    payload = json.loads(overlay_path.read_text(encoding="utf-8"))
    validate_document("portfolio-p0-currentness", payload)

    corpus_bytes = corpus_path.read_bytes()
    observed_blob = _git_blob_sha(corpus_bytes)
    binding = payload["corpus_binding"]
    if binding["git_blob_sha"] != observed_blob:
        raise ValueError("P0 currentness overlay corpus blob binding mismatch")

    corpus = load_portfolio_corpus(corpus_path, public_safe=True)
    expected = {
        record.id: (record.repository, record.default_branch)
        for record in corpus.records
        if record.priority == "P0"
    }

    subjects = payload["subjects"]
    subject_ids = [str(item["subject_id"]) for item in subjects]
    repositories = [str(item["repository"]) for item in subjects]
    if len(subject_ids) != len(set(subject_ids)):
        raise ValueError("duplicate P0 currentness subject id")
    if len(repositories) != len(set(repositories)):
        raise ValueError("duplicate P0 currentness repository")

    if payload["coverage"]["repository_count"] != len(subjects):
        raise ValueError("P0 currentness coverage count does not match subjects")
    if len(subjects) != len(expected):
        raise ValueError("P0 currentness overlay does not cover exact corpus P0 set")
    if set(subject_ids) != set(expected):
        raise ValueError("P0 currentness overlay subject membership mismatch")

    for item in subjects:
        subject_id = str(item["subject_id"])
        expected_repository, expected_branch = expected[subject_id]
        if item["repository"] != expected_repository:
            raise ValueError(
                f"P0 currentness repository mismatch for {subject_id}"
            )
        if item["default_branch"] != expected_branch:
            raise ValueError(
                f"P0 currentness default branch mismatch for {subject_id}"
            )

    return payload
