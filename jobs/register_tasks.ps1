# Registers Windows Task Scheduler jobs for dlt-evolution-lab (idempotent by task name).
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonExe = "python",
    [string]$TaskPrefix = "DLT-EvolutionLab"
)

$ErrorActionPreference = "Stop"
$schedulerPy = Join-Path $RepoRoot "jobs\scheduler_service.py"

function Register-OrUpdateTask {
    param(
        [string]$TaskName,
        [string]$TriggerCommand,
        [string]$Schedule,
        [string]$StartTime,
        [string]$Days = "",
        [string]$RepeatEveryMinutes = "",
        [string]$RepeatDuration = ""
    )

    $createArgs = @(
        "/Create",
        "/TN", $TaskName,
        "/TR", "`"$PythonExe`" `"$schedulerPy`" $TriggerCommand",
        "/SC", $Schedule,
        "/ST", $StartTime,
        "/F"
    )

    if ($Days) {
        $createArgs += @("/D", $Days)
    }
    if ($RepeatEveryMinutes) {
        $createArgs += @("/RI", $RepeatEveryMinutes)
    }
    if ($RepeatDuration) {
        $createArgs += @("/DU", $RepeatDuration)
    }

    schtasks @createArgs | Out-Host
    Write-Host "Registered: $TaskName"
}

# M5 fixed schedule baseline
# 1) Daily 09:00 sync
Register-OrUpdateTask `
    -TaskName "$TaskPrefix-sync-daily-0900" `
    -TriggerCommand "sync_job --trigger schedule" `
    -Schedule "DAILY" `
    -StartTime "09:00"

# 2) Mon/Wed/Sat 20:30 publish check (auto resolve next issue in scheduler_service.py)
Register-OrUpdateTask `
    -TaskName "$TaskPrefix-publish-check-2030" `
    -TriggerCommand "publish_check_job --trigger schedule" `
    -Schedule "WEEKLY" `
    -Days "MON,WED,SAT" `
    -StartTime "20:30"

# 3) Mon/Wed/Sat 21:45 draw polling, repeat every 5 minutes for 2 hours
Register-OrUpdateTask `
    -TaskName "$TaskPrefix-draw-poll-2145-5m" `
    -TriggerCommand "draw_poll_job --trigger schedule" `
    -Schedule "WEEKLY" `
    -Days "MON,WED,SAT" `
    -StartTime "21:45" `
    -RepeatEveryMinutes "5" `
    -RepeatDuration "02:00"

Write-Host "Done. Tasks now match M5 schedule constraints (09:00, 20:30, 21:45/5m poll)."
