from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from .task_monitor import finalize_task, register_task


REQUEST_SCHEMA = "PROJECT_RUNNER_TASK_LAUNCH_REQUEST_V1"


def _windows_current_process_started_at_utc() -> str | None:
    if os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.restype = wintypes.HANDLE
    get_process_times = kernel32.GetProcessTimes
    get_process_times.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    get_process_times.restype = wintypes.BOOL

    if not get_process_times(
        get_current_process(),
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        return None

    ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    started = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(
        microseconds=ticks / 10
    )
    return started.isoformat()


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def run_supervisor(request_path: Path) -> int:
    request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError("unsupported task launch request schema")

    tasks_root = Path(str(request["tasks_root"])).resolve()
    working_directory = Path(str(request["working_directory"])).resolve()
    stdout_log = Path(str(request["stdout_log"])).resolve()
    stderr_log = Path(str(request["stderr_log"])).resolve()
    ack_path = Path(str(request["ack_path"])).resolve()

    record = register_task(
        tasks_root,
        name=str(request["name"]),
        pid=os.getpid(),
        owner=str(request["owner"]),
        repository=request.get("repository"),
        worktree=request.get("worktree"),
        lane=request.get("lane"),
        work_unit=request.get("work_unit"),
        command=str(request.get("display_command") or request["command"]),
        working_directory=str(working_directory),
        process_started_at_utc=_windows_current_process_started_at_utc(),
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )
    task_id = str(record["task_id"])

    _atomic_json_write(
        ack_path,
        {
            "mode": "PROJECT_RUNNER_TASK_SUPERVISOR_V2",
            "launch_id": str(request["launch_id"]),
            "task_id": task_id,
            "supervisor_pid": os.getpid(),
            "name": str(request["name"]),
            "tasks_root": str(tasks_root),
        },
    )
    request_path.unlink(missing_ok=True)

    stdout_log.parent.mkdir(parents=True, exist_ok=True)
    stderr_log.parent.mkdir(parents=True, exist_ok=True)
    command = str(request["command"])
    encoded_command = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
    powershell_exe = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )

    try:
        with stdout_log.open("wb") as stdout_handle, stderr_log.open("wb") as stderr_handle:
            child = subprocess.Popen(
                [
                    str(powershell_exe),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded_command,
                ],
                cwd=working_directory,
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
            exit_code = int(child.wait())
    except BaseException:
        finalize_task(
            tasks_root,
            task_id=task_id,
            exit_code=125,
            terminal_reason="LAUNCH_FAILED",
        )
        raise

    finalize_task(
        tasks_root,
        task_id=task_id,
        exit_code=exit_code,
        terminal_reason="PROCESS_EXITED",
    )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project-runner-task-supervisor")
    parser.add_argument("--request-path", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_supervisor(args.request_path)


if __name__ == "__main__":
    raise SystemExit(main())
