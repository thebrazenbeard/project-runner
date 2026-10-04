import json
import os

from runner.cli import main


def test_task_register_and_status_round_trip(tmp_path, capsys):
    tasks_root = tmp_path / "tasks"

    assert main([
        "task-register",
        "--tasks-root", str(tasks_root),
        "--name", "model-training-lane-b",
        "--pid", str(os.getpid()),
        "--owner", "chatgpt",
        "--repository", "thebrazenbeard/vera_model_training",
        "--lane", "lane-b",
        "--command", "python train.py",
    ]) == 0
    registered = json.loads(capsys.readouterr().out)
    task_id = registered["task"]["task_id"]
    assert registered["task"]["name"] == "model-training-lane-b"
    assert registered["task"]["pid"] == os.getpid()

    assert main([
        "task-status",
        "--tasks-root", str(tasks_root),
    ]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["mode"] == "PROJECT_RUNNER_TASK_MONITOR_V1"
    assert status["tasks"] == [{
        **registered["task"],
        "state": "RUNNING",
    }]
    assert (tasks_root / "active" / f"{task_id}.json").exists()
