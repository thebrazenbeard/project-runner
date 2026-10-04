from __future__ import annotations

from datetime import datetime, timezone
import errno
import json
import os
import re
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4


TASK_SCHEMA = "PROJECT_RUNNER_LOCAL_TASK_V1"
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN_EXIT"}


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


def finalize_task(
    tasks_root: Path,
    *,
    task_id: str,
    exit_code: int,
    terminal_reason: str = "PROCESS_EXITED",
) -> dict[str, Any]:
    return _archive_terminal_task(
        tasks_root,
        task_id=task_id,
        state="COMPLETED" if exit_code == 0 else "FAILED",
        exit_code=exit_code,
        terminal_reason=terminal_reason,
    )


def reconcile_orphaned_tasks(tasks_root: Path) -> list[dict[str, Any]]:
    active = Path(tasks_root) / "active"
    reconciled: list[dict[str, Any]] = []
    if not active.exists():
        return reconciled

    for path in sorted(active.glob("*.json")):
        record = _load_task_record(path)
        if record is None:
            continue
        if _process_is_running(int(record["pid"])):
            continue
        reconciled.append(
            _archive_terminal_task(
                tasks_root,
                task_id=str(record["task_id"]),
                state="UNKNOWN_EXIT",
                exit_code=None,
                terminal_reason="PROCESS_GONE_WITHOUT_FINAL_RECEIPT",
            )
        )
    return reconciled


def summarize_tasks(tasks_root: Path) -> dict[str, Any]:
    active = Path(tasks_root) / "active"
    tasks: list[dict[str, Any]] = []
    if active.exists():
        for path in sorted(active.glob("*.json")):
            record = _load_task_record(path)
            if record is None:
                continue
            task = dict(record)
            task["state"] = "RUNNING" if _process_is_running(int(task["pid"])) else "ORPHANED"
            tasks.append(task)
    return {
        "mode": "PROJECT_RUNNER_TASK_MONITOR_V1",
        "tasks": tasks,
    }


def summarize_task_history(tasks_root: Path) -> dict[str, Any]:
    history = Path(tasks_root) / "history"
    tasks: list[dict[str, Any]] = []
    if history.exists():
        for path in sorted(history.glob("*.json")):
            record = _load_task_record(path)
            if record is None:
                continue
            tasks.append(record)
    tasks.sort(key=lambda item: str(item.get("ended_at_utc") or ""), reverse=True)
    return {
        "mode": "PROJECT_RUNNER_TASK_HISTORY_V1",
        "tasks": tasks,
    }


def _archive_terminal_task(
    tasks_root: Path,
    *,
    task_id: str,
    state: str,
    exit_code: int | None,
    terminal_reason: str,
) -> dict[str, Any]:
    if state not in TERMINAL_STATES:
        raise ValueError(f"invalid terminal task state: {state}")
    if re.fullmatch(r"[0-9a-f]{32}", task_id) is None:
        raise ValueError("invalid task id")

    root = Path(tasks_root)
    active_path = root / "active" / f"{task_id}.json"
    history = root / "history"
    history_path = history / f"{task_id}.json"

    if not active_path.exists():
        if history_path.exists():
            record = _load_task_record(history_path)
            if record is None:
                raise ValueError(f"invalid historical task record: {task_id}")
            return record
        raise ValueError(f"active task not found: {task_id}")

    record = _load_task_record(active_path)
    if record is None:
        raise ValueError(f"invalid active task record: {task_id}")
    if str(record.get("task_id")) != task_id:
        raise ValueError("task id does not match active record")

    ended = datetime.now(timezone.utc)
    record["state"] = state
    record["status"] = state
    record["exit_code"] = exit_code
    record["terminal_reason"] = terminal_reason
    record["ended_at_utc"] = ended.isoformat()

    started_raw = record.get("started_at_utc")
    if isinstance(started_raw, str):
        try:
            started = datetime.fromisoformat(started_raw)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            record["duration_seconds"] = max(
                0.0, (ended - started.astimezone(timezone.utc)).total_seconds()
            )
        except ValueError:
            record["duration_seconds"] = None
    else:
        record["duration_seconds"] = None

    history.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(active_path, record)
    os.replace(active_path, history_path)
    return record


def _load_task_record(path: Path) -> dict[str, Any] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or record.get("schema") != TASK_SCHEMA:
        return None
    return record


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
