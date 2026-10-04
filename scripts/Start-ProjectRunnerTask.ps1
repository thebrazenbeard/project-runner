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
New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null

$launchId = [guid]::NewGuid().ToString("N")
$stdoutLog = Join-Path $logsRoot "$launchId.stdout.log"
$stderrLog = Join-Path $logsRoot "$launchId.stderr.log"
$encodedCommand = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($Command)
)

$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$process = $null
try {
    $process = Start-Process -FilePath $powershellExe `
        -ArgumentList @("-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", $encodedCommand) `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    $shownCommand = if ([string]::IsNullOrWhiteSpace($DisplayCommand)) {
        $Command
    } else {
        $DisplayCommand
    }

    $registerArgs = @(
        "task-register",
        "--tasks-root", $TasksRoot,
        "--name", $Name,
        "--pid", [string]$process.Id,
        "--owner", $Owner,
        "--command", $shownCommand,
        "--working-directory", $WorkingDirectory,
        "--process-started-at-utc", $process.StartTime.ToUniversalTime().ToString("o"),
        "--stdout-log", $stdoutLog,
        "--stderr-log", $stderrLog
    )
    if ($Repository) { $registerArgs += @("--repository", $Repository) }
    if ($Worktree) { $registerArgs += @("--worktree", $Worktree) }
    if ($Lane) { $registerArgs += @("--lane", $Lane) }
    if ($WorkUnit) { $registerArgs += @("--work-unit", $WorkUnit) }

    $runnerCommand = Get-Command project-runner -ErrorAction SilentlyContinue
    if ($null -ne $runnerCommand) {
        $registration = & $runnerCommand.Source @registerArgs
    }
    elseif ($null -ne (Get-Command py -ErrorAction SilentlyContinue)) {
        $registration = & py -m runner.cli @registerArgs
    }
    elseif ($null -ne (Get-Command python -ErrorAction SilentlyContinue)) {
        $registration = & python -m runner.cli @registerArgs
    }
    else {
        throw "Project Runner is installed but no usable Python launcher was found"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "project-runner task registration failed with exit code $LASTEXITCODE"
    }

    $registration
}
catch {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    throw
}
