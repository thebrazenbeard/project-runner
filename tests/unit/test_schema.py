import pytest
from jsonschema import ValidationError
from runner.schema import validate_document


def test_worker_schema_rejects_missing_id():
    with pytest.raises(ValidationError):
        validate_document("worker", {"workers": [{"name": "missing id"}]})


def test_project_schema_accepts_minimal_project():
    validate_document("project", {
        "projects": [{
            "id": "project-runner",
            "name": "Project Runner",
            "visibility": "public",
            "repositories": ["thebrazenbeard/project-runner"],
            "capabilities": ["read", "analyze", "propose", "write_branch"]
        }]
    })
