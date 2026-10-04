[CmdletBinding()]
param(
    [string]$TasksRoot,
    [ValidateRange(1, 3600)]
    [int]$RefreshSeconds = 2,
    [switch]$Once,
    [switch]$IncludeCommand
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ProjectRunnerTasksRoot {
    param([string]$RequestedRoot)

    if (-not [string]::IsNullOrWhiteSpace($RequestedRoot)) {
        return [System.IO.Path]::GetFullPath($RequestedRoot)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:PROJECT_RUNNER_TASKS_ROOT)) {
        return [System.IO.Path]::GetFullPath($env:PROJECT_RUNNER_TASKS_ROOT)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        return (Join-Path $env:LOCALAPPDATA "ProjectRunner\tasks")
    }
    return (Join-Path $HOME ".project-runner\tasks")
}

function Get-DescendantProcessIds {
    param(
        [int]$RootPid,
        [object[]]$ProcessRows
    )

    $seen = New-Object 'System.Collections.Generic.HashSet[int]'
    $queue = New-Object 'System.Collections.Generic.Queue[int]'
    $queue.Enqueue($RootPid)

    while ($queue.Count -gt 0) {
        $parent = $queue.Dequeue()
        foreach ($row in $ProcessRows) {
            if ([int]$row.ParentProcessId -eq $parent) {
                $child = [int]$row.ProcessId
                if ($seen.Add($child)) {
                    $queue.Enqueue($child)
                }
            }
        }
    }
    return @($seen)
}

function Test-RootProcessIdentity {
    param(
        [object]$Task,
        [System.Diagnostics.Process]$Process
    )

    if ($null -eq $Process) { return $false }
    if ([string]::IsNullOrWhiteSpace([string]$Task.process_started_at_utc)) {
        return $true
    }

    try {
        $expected = [DateTimeOffset]::Parse([string]$Task.process_started_at_utc).UtcDateTime
        $actual = $Process.StartTime.ToUniversalTime()
        return [Math]::Abs(($actual - $expected).TotalSeconds) -lt 1.0
    }
    catch {
        return $false
    }
}

$TasksRoot = Resolve-ProjectRunnerTasksRoot $TasksRoot
$activeRoot = Join-Path $TasksRoot "active"

do {
    $now = [DateTimeOffset]::UtcNow
    $processRows = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Select-Object ProcessId, ParentProcessId
    )
    $rows = @()

    if (Test-Path $activeRoot) {
        foreach ($file in Get-ChildItem -Path $activeRoot -Filter "*.json" -File) {
            try {
                $task = Get-Content -Raw -Path $file.FullName | ConvertFrom-Json
                if ($task.schema -ne "PROJECT_RUNNER_LOCAL_TASK_V1") { continue }

                $rootProcess = Get-Process -Id ([int]$task.pid) -ErrorAction SilentlyContinue
                $identityMatches = Test-RootProcessIdentity -Task $task -Process $rootProcess
                if ($null -ne $rootProcess -and -not $identityMatches) {
                    $state = "PID_REUSED"
                    $liveProcesses = @()
                }
                elseif ($null -eq $rootProcess) {
                    $state = "ORPHANED"
                    $liveProcesses = @()
                }
                else {
                    $state = "RUNNING"
                    $treePids = @([int]$task.pid)
                    $treePids += @(Get-DescendantProcessIds -RootPid ([int]$task.pid) -ProcessRows $processRows)
                    $liveProcesses = @(
                        $treePids |
                            Sort-Object -Unique |
                            ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue } |
                            Where-Object { $null -ne $_ }
                    )
                }

                $cpuSeconds = ($liveProcesses | Measure-Object -Property CPU -Sum).Sum
                $ramBytes = ($liveProcesses | Measure-Object -Property WorkingSet64 -Sum).Sum
                if ($null -eq $cpuSeconds) { $cpuSeconds = 0 }
                if ($null -eq $ramBytes) { $ramBytes = 0 }

                try {
                    $started = [DateTimeOffset]::Parse([string]$task.started_at_utc)
                    $runtime = $now - $started
                    $runtimeText = "{0:00}:{1:00}:{2:00}" -f [Math]::Floor($runtime.TotalHours), $runtime.Minutes, $runtime.Seconds
                }
                catch {
                    $runtimeText = "UNKNOWN"
                }

                $row = [ordered]@{
                    Task = [string]$task.name
                    PID = [int]$task.pid
                    State = $state
                    Runtime = $runtimeText
                    CPU_s = [Math]::Round([double]$cpuSeconds, 1)
                    RAM_MB = [Math]::Round(([double]$ramBytes / 1MB), 1)
                    Children = [Math]::Max(0, $liveProcesses.Count - 1)
                    Repo = [string]$task.repository
                    Lane = [string]$task.lane
                    Owner = [string]$task.owner
                }
                if ($IncludeCommand) {
                    $row["Command"] = [string]$task.command
                }
                $rows += [pscustomobject]$row
            }
            catch {
                $rows += [pscustomobject]@{
                    Task = $file.BaseName
                    PID = ""
                    State = "INVALID_RECORD"
                    Runtime = ""
                    CPU_s = ""
                    RAM_MB = ""
                    Children = ""
                    Repo = ""
                    Lane = ""
                    Owner = ""
                }
            }
        }
    }

    if (-not $Once) { Clear-Host }
    Write-Host "Project Runner Task Monitor  |  $TasksRoot"
    Write-Host "Updated: $($now.ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss zzz'))"
    Write-Host ""

    if ($rows.Count -eq 0) {
        Write-Host "No registered Project Runner tasks."
    }
    else {
        $rows |
            Sort-Object State, Task, PID |
            Format-Table -AutoSize
    }

    if ($Once) { break }
    Start-Sleep -Seconds $RefreshSeconds
} while ($true)
