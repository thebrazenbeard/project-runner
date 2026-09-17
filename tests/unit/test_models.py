from runner.models import WorkerDefinition, WorkerLifecycle


def test_worker_locator_defaults_to_registered_only():
    worker = WorkerDefinition.from_mapping({
        "id": "tkal-in-ket-quorum",
        "name": "T'Kal-in-ket Quorum",
        "worker_type": "CHATGPT_CUSTOM_GPT",
        "lifecycle": "REGISTERED",
        "locators": {"gpt_id": "g-68c3e43aabc4819180ef0a89a10c4eb6"},
        "routes": {},
        "roles": [],
    })
    assert worker.lifecycle is WorkerLifecycle.REGISTERED


def test_invalid_gpt_id_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="GPT id"):
        WorkerDefinition.from_mapping({
            "id": "bad",
            "name": "Bad",
            "worker_type": "CHATGPT_CUSTOM_GPT",
            "lifecycle": "REGISTERED",
            "locators": {"gpt_id": "not-a-gpt-id"},
            "routes": {},
            "roles": [],
        })


def test_executable_worker_requires_verified_route():
    import pytest
    with pytest.raises(ValueError, match="EXECUTABLE"):
        WorkerDefinition.from_mapping({
            "id": "tkal",
            "name": "T'Kal",
            "worker_type": "CHATGPT_CUSTOM_GPT",
            "lifecycle": "EXECUTABLE",
            "locators": {"gpt_id": "g-68c3e43aabc4819180ef0a89a10c4eb6"},
            "routes": {"RUNNER_ACTION_PULL": "UNVERIFIED"},
            "roles": ["hostile_review"],
        })
