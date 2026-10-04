[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [Parameter(Mandatory = $true)]
    [string]$Command,

    [string]$Repository,
    [string]$Worktree,
    [string]$Lane,
    [string]$Owner = "chatgpt",
    [string]$WorkUnit,
    [string]$DisplayCommand,
    [string]$WorkingDirectory = (Get-Location).Path,
    [string]$TasksRoot
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

$TasksRoot = Resolve-ProjectRunnerTasksRoot $TasksRoot
$WorkingDirectory = [System.IO.Path]::GetFullPath($WorkingDirectory)
$logsRoot = Join-Path $TasksRoot "logs"
$requestsRoot = Join-Path $TasksRoot "requests"
$launchesRoot = Join-Path $TasksRoot "launches"
New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $requestsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $launchesRoot -Force | Out-Null

$launchId = [guid]::NewGuid().ToString("N")
$stdoutLog = Join-Path $logsRoot "$launchId.stdout.log"
$stderrLog = Join-Path $logsRoot "$launchId.stderr.log"
$supervisorStdout = Join-Path $logsRoot "$launchId.supervisor.stdout.log"
$supervisorStderr = Join-Path $logsRoot "$launchId.supervisor.stderr.log"
$requestPath = Join-Path $requestsRoot "$launchId.json"
$ackPath = Join-Path $launchesRoot "$launchId.json"

$request = [ordered]@{
    schema = "PROJECT_RUNNER_TASK_LAUNCH_REQUEST_V1"
    launch_id = $launchId
    name = $Name
    command = $Command
    display_command = $DisplayCommand
    repository = $Repository
    worktree = $Worktree
    lane = $Lane
    owner = $Owner
    work_unit = $WorkUnit
    working_directory = $WorkingDirectory
    tasks_root = $TasksRoot
    stdout_log = $stdoutLog
    stderr_log = $stderrLog
    ack_path = $ackPath
}
$request | ConvertTo-Json -Depth 4 | Set-Content -Path $requestPath -Encoding UTF8

$supervisorPath = Join-Path $PSScriptRoot "Invoke-ProjectRunnerTaskSupervisor.ps1"
if (-not (Test-Path $supervisorPath)) {
    throw "Project Runner task supervisor is missing: $supervisorPath"
}

$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$supervisor = Start-Process -FilePath $powershellExe `
    -ArgumentList @(
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-File", $supervisorPath,
        "-RequestPath", $requestPath
    ) `
    -WorkingDirectory $WorkingDirectory `
    -RedirectStandardOutput $supervisorStdout `
    -RedirectStandardError $supervisorStderr `
    -PassThru

$deadline = [DateTime]::UtcNow.AddSeconds(5)
while ([DateTime]::UtcNow -lt $deadline -and -not (Test-Path $ackPath)) {
    if ($supervisor.HasExited) {
        $detail = if (Test-Path $supervisorStderr) {
            Get-Content -Raw -Path $supervisorStderr
        } else {
            ""
        }
        throw "task supervisor exited before registration (exit $($supervisor.ExitCode)): $detail"
    }
    Start-Sleep -Milliseconds 50
}

if (-not (Test-Path $ackPath)) {
    throw "task supervisor did not confirm registration within 5 seconds; PID $($supervisor.Id)"
}

Get-Content -Raw -Path $ackPath
