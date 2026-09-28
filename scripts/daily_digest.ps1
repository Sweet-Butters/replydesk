# 아침마다 받은편지함을 판단해 요약을 카카오톡 '나와의 채팅'으로 보낸다.
#
# 작업 스케줄러가 부르는 진입점이다. 스케줄러는 사람의 셸 환경을 물려받지 않으므로, 키 경로는
# 여기서 저장소 기준으로 직접 만든다. 이 파일에는 비밀값이 없고 경로만 있다.
#
#   등록:  scripts\register_daily_digest.ps1
#   수동:  powershell -ExecutionPolicy Bypass -File scripts\daily_digest.ps1
#
# 실패해도 조용히 죽지 않는다. 로그가 남고, 카카오가 살아 있으면 실패 사실도 폰으로 간다.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$logDir = Join-Path $root 'logs'
$log = Join-Path $logDir ('digest-{0}.log' -f (Get-Date -Format 'yyyy-MM'))
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log([string]$text) {
    "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $text | Tee-Object -FilePath $log -Append
}

# 키는 저장소 안 keys/ 에 있다 (.gitignore 로 막혀 있음). 없으면 그 사실을 로그에 남기고 끝낸다.
$keys = @{
    'TYPESAFE_API_KEY_FILE'   = Join-Path $root 'keys\typesafe_api_key.txt'
    'KAKAO_REST_API_KEY_FILE' = Join-Path $root 'keys\kakao_rest_api_key.txt'
    'KAKAO_CLIENT_SECRET_FILE' = Join-Path $root 'keys\kakao_client_secret.txt'
}
foreach ($name in $keys.Keys) {
    if (Test-Path $keys[$name]) {
        Set-Item -Path "env:$name" -Value $keys[$name]
    } elseif ($name -eq 'KAKAO_CLIENT_SECRET_FILE') {
        continue                       # 시크릿을 '사용 안 함'으로 둔 앱이면 없는 게 정상
    } else {
        Write-Log "중단: 키 파일이 없습니다 — $($keys[$name])"
        exit 2
    }
}

Write-Log '시작'
# 파이썬은 경고를 stderr 로 낸다. ErrorActionPreference 가 Stop 인 채로 외부 명령을 부르면
# 그 경고 한 줄이 NativeCommandError 로 승격돼, 요약은 멀쩡히 나갔는데 작업은 실패로 끝난다.
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

# 어제 요약에 단 답장("2번 초안")을 먼저 처리한다. 순서가 중요하다 — 새 요약을 먼저 보내면
# 번호표가 덮어써져서, 회신이 가리키던 번호가 다른 메일을 가리키게 된다.
$replies = & $python -m replydesk commands --channel gmail 2>&1
$replies | Where-Object { $_ -notmatch 'FutureWarning|warnings\.warn|^\s*$' } |
    ForEach-Object { Write-Log "  [회신] $_" }

$out = & $python -m replydesk digest --channel gmail --account yonsei,personal --notify kakao --mail 2>&1
$code = $LASTEXITCODE
$ErrorActionPreference = $prev
$out | Where-Object { $_ -notmatch 'FutureWarning|warnings\.warn|^\s*$' } |
    ForEach-Object { Write-Log "  $_" }

if ($code -ne 0) {
    Write-Log "실패 (종료코드 $code)"
    # 조용한 실패가 제일 나쁘다: 알림 경로가 살아 있으면 실패했다는 사실 자체를 보낸다.
    try {
        & $python -m replydesk.notify.kakao --test 2>&1 | Out-Null
        $msg = "[replydesk] 아침 요약이 실패했습니다 (코드 $code). 로그: logs\"
        & $python -c "import sys; sys.path.insert(0,'.'); from replydesk.notify import kakao; kakao.send(sys.argv[1])" $msg 2>&1 | Out-Null
    } catch { Write-Log '  실패 알림도 보내지 못했습니다' }
}
Write-Log "끝 (종료코드 $code)"
exit $code
