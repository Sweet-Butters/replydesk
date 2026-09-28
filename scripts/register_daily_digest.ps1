# 아침 요약을 Windows 작업 스케줄러에 등록한다. 관리자 권한은 필요 없다.
#
#   등록:  powershell -ExecutionPolicy Bypass -File scripts\register_daily_digest.ps1
#   시각:  -At 08:30   (기본 08:00)
#   해제:  Unregister-ScheduledTask -TaskName replydesk-daily-digest -Confirm:$false
#
# StartWhenAvailable 을 켜는 이유: 그 시각에 PC가 꺼져 있으면 작업은 그냥 사라진다. 아침 요약은
# 늦게라도 오는 편이 낫지, 컴퓨터를 언제 켰는지에 따라 있다 없다 하는 편이 낫지 않다.

param(
    [string]$At = '08:00',
    [string]$TaskName = 'replydesk-daily-digest'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'daily_digest.ps1'
if (-not (Test-Path $script)) { throw "실행 스크립트가 없습니다: $script" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description '받은편지함을 판단해 요약을 카카오톡 나와의 채팅으로 보냅니다 (replydesk)' `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "등록했습니다: $TaskName"
Write-Host "  매일 $At · 상태 $($task.State)"
Write-Host "  다음 실행: $($info.NextRunTime)"
Write-Host ""
Write-Host "지금 한 번 돌려보기: Start-ScheduledTask -TaskName $TaskName"
Write-Host "해제:              Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
