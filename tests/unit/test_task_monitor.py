import json
import os
from pathlib import Path

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


def test_windows_task_launcher_and_read_only_monitor_are_shipped():
    root = Path(__file__).resolve().parents[2]
    launcher_path = root / "scripts" / "Start-ProjectRunnerTask.ps1"
    monitor_path = root / "scripts" / "Watch-ProjectRunnerTasks.ps1"

    assert launcher_path.exists()
    assert monitor_path.exists()

    launcher = launcher_path.read_text(encoding="utf-8")
    monitor = monitor_path.read_text(encoding="utf-8")
    assert "Start-Process" in launcher
    assert "task-register" in launcher
    assert "EncodedCommand" in launcher
    assert "Get-CimInstance Win32_Process" in monitor
    assert "Stop-Process" not in monitor
    assert "Remove-Item" not in monitor
