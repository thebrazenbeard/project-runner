[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RequestPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-ProjectRunnerCli {
    param([string[]]$Arguments)

    $runnerCommand = Get-Command project-runner -ErrorAction SilentlyContinue
    if ($null -ne $runnerCommand) {
        $output = @(& $runnerCommand.Source @Arguments)
    }
    elseif ($null -ne (Get-Command py -ErrorAction SilentlyContinue)) {
        $output = @(& py -m runner.cli @Arguments)
    }
    elseif ($null -ne (Get-Command python -ErrorAction SilentlyContinue)) {
        $output = @(& python -m runner.cli @Arguments)
    }
    else {
        throw "Project Runner is installed but no usable Python launcher was found"
    }

    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "project-runner command failed with exit code $exitCode"
    }
    return ($output -join [Environment]::NewLine)
}

$request = Get-Content -Raw -Path $RequestPath | ConvertFrom-Json
if ([string]$request.schema -ne "PROJECT_RUNNER_TASK_LAUNCH_REQUEST_V1") {
    throw "unsupported task launch request schema"
}

$tasksRoot = [System.IO.Path]::GetFullPath([string]$request.tasks_root)
$workingDirectory = [System.IO.Path]::GetFullPath([string]$request.working_directory)
$stdoutLog = [string]$request.stdout_log
$stderrLog = [string]$request.stderr_log
$ackPath = [string]$request.ack_path
$shownCommand = if ([string]::IsNullOrWhiteSpace([string]$request.display_command)) {
    [string]$request.command
} else {
    [string]$request.display_command
}

$self = Get-Process -Id $PID
$registerArgs = @(
    "task-register",
    "--tasks-root", $tasksRoot,
    "--name", [string]$request.name,
    "--pid", [string]$PID,
    "--owner", [string]$request.owner,
    "--command", $shownCommand,
    "--working-directory", $workingDirectory,
    "--process-started-at-utc", $self.StartTime.ToUniversalTime().ToString("o"),
    "--stdout-log", $stdoutLog,
    "--stderr-log", $stderrLog
)
if ($request.repository) { $registerArgs += @("--repository", [string]$request.repository) }
if ($request.worktree) { $registerArgs += @("--worktree", [string]$request.worktree) }
if ($request.lane) { $registerArgs += @("--lane", [string]$request.lane) }
if ($request.work_unit) { $registerArgs += @("--work-unit", [string]$request.work_unit) }

$registrationRaw = Invoke-ProjectRunnerCli -Arguments $registerArgs
$registration = $registrationRaw | ConvertFrom-Json
$taskId = [string]$registration.task.task_id

$ack = [ordered]@{
    mode = "PROJECT_RUNNER_TASK_SUPERVISOR_V1"
    launch_id = [string]$request.launch_id
    task_id = $taskId
    supervisor_pid = $PID
    name = [string]$request.name
    tasks_root = $tasksRoot
}
$ackDirectory = Split-Path -Parent $ackPath
New-Item -ItemType Directory -Path $ackDirectory -Force | Out-Null
$ackTemp = "$ackPath.tmp.$PID"
$ack | ConvertTo-Json -Compress | Set-Content -Path $ackTemp -Encoding UTF8
Move-Item -Path $ackTemp -Destination $ackPath -Force

Remove-Item -Path $RequestPath -Force -ErrorAction SilentlyContinue

$encodedCommand = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes([string]$request.command)
)
$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$exitReceiptsRoot = Join-Path $tasksRoot "exit-receipts"
New-Item -ItemType Directory -Path $exitReceiptsRoot -Force | Out-Null
$exitReceiptPath = Join-Path $exitReceiptsRoot "$taskId.txt"

# Windows PowerShell can lose Process.ExitCode when Start-Process also owns
# stdout/stderr redirection. Run the requested command in a nested child whose
# wrapper records the authoritative exit code before the redirected wrapper exits.
$receiptLiteral = $exitReceiptPath.Replace("'", "''")
$exeLiteral = $powershellExe.Replace("'", "''")
$wrapperCommand = @"
`$inner = Start-Process -FilePath '$exeLiteral' -ArgumentList @('-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand','$encodedCommand') -NoNewWindow -PassThru
`$inner.WaitForExit()
`$code = [int]`$inner.ExitCode
Set-Content -LiteralPath '$receiptLiteral' -Value `$code -Encoding ASCII
exit `$code
"@
$wrapperEncoded = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($wrapperCommand)
)

try {
    $child = Start-Process -FilePath $powershellExe `
        -ArgumentList @("-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", $wrapperEncoded) `
        -WorkingDirectory $workingDirectory `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    $child.WaitForExit()
    if (-not (Test-Path $exitReceiptPath)) {
        throw "task command exited without an exit-code receipt"
    }
    $exitCode = [int](Get-Content -Raw -Path $exitReceiptPath).Trim()
    Remove-Item -Path $exitReceiptPath -Force -ErrorAction SilentlyContinue
}
catch {
    Write-Error $_
    $exitCode = 125
}

$finalizeArgs = @(
    "task-finalize",
    "--tasks-root", $tasksRoot,
    "--task-id", $taskId,
    "--exit-code", [string]$exitCode
)
Invoke-ProjectRunnerCli -Arguments $finalizeArgs | Out-Null
exit $exitCode
