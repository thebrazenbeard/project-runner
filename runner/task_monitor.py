from __future__ import annotations

from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4


TASK_SCHEMA = "PROJECT_RUNNER_LOCAL_TASK_V1"


def register_task(
    tasks_root: Path,
    *,
    name: str,
    pid: int,
    owner: str,
    repository: str | None = None,
    worktree: str | None = None,
    lane: str | None = None,
    work_unit: str | None = None,
    command: str | None = None,
    working_directory: str | None = None,
    process_started_at_utc: str | None = None,
    stdout_log: str | None = None,
    stderr_log: str | None = None,
) -> dict[str, Any]:
    if pid <= 0:
        raise ValueError("task pid must be positive")
    if not name.strip():
        raise ValueError("task name must not be empty")
    if not owner.strip():
        raise ValueError("task owner must not be empty")

    active = Path(tasks_root) / "active"
    active.mkdir(parents=True, exist_ok=True)
    task_id = uuid4().hex
    record: dict[str, Any] = {
        "schema": TASK_SCHEMA,
        "task_id": task_id,
        "name": name,
        "pid": pid,
        "owner": owner,
        "repository": repository,
        "worktree": worktree,
        "lane": lane,
        "work_unit": work_unit,
        "command": command,
        "working_directory": working_directory,
        "process_started_at_utc": process_started_at_utc,
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "REGISTERED",
    }
    _atomic_json_write(active / f"{task_id}.json", record)
    return record


def summarize_tasks(tasks_root: Path) -> dict[str, Any]:
    active = Path(tasks_root) / "active"
    tasks: list[dict[str, Any]] = []
    if active.exists():
        for path in sorted(active.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("schema") != TASK_SCHEMA:
                continue
            task = dict(record)
            task["state"] = "RUNNING" if _process_is_running(int(task["pid"])) else "ORPHANED"
            tasks.append(task)
    return {
        "mode": "PROJECT_RUNNER_TASK_MONITOR_V1",
        "tasks": tasks,
    }


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
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


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_process_is_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def _windows_process_is_running(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    get_exit_code = kernel32.GetExitCodeProcess
    get_exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    get_exit_code.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = open_process(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not get_exit_code(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        close_handle(handle)
