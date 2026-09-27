# replydesk — status board

> **Last updated:** 2026-09-28 07:05
> Update this file in the same commit as the work. Change the summary and the time above,
> not only the log. Entries carry a time and who did it.

## Summary

이메일 채널이 실제 메일함에서 끝까지 동작합니다. 두 개의 Gmail 계정이 연결돼 있고(읽기·초안·발송),
판단 → 초안 3개 → 순위 → 사람이 발송까지 확인했습니다. 다음 작업은 (1) 실제 메일로 초안을 만들어
임시보관함까지 넣어 보기, (2) 판단 정확도를 실제 메일 30~50건으로 측정하기입니다.
샘플 받은편지함만 쓰면 키 없이도 구조를 볼 수 있습니다.

## Setting this up on another machine

이 저장소에는 키도 토큰도 없습니다. 새 컴퓨터에서는 아래가 필요합니다.

| 필요한 것 | 어디서 | 없으면 |
|---|---|---|
| `TYPESAFE_API_KEY` | https://console.typesafe.ai/keys | 판단 불가(전부 막힘) |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey | 초안 생성만 불가, 분류는 동작 |
| Gmail OAuth 클라이언트 JSON | Google Cloud → 해당 프로젝트 → 사용자 인증 정보 | 샘플 받은편지함만 사용 가능 |
| Gmail 토큰 | `python -m replydesk.connect --account <메일>` 로 새로 발급 | — |

```bash
git clone https://github.com/Sweet-Butters/replydesk && cd replydesk
python -m venv .venv && .venv/Scripts/pip install -e ".[gmail]" pytest
python -m pytest tests -q                 # 21개, 네트워크 불필요
python -m replydesk triage                # 샘플 받은편지함, 키 없이 구조 확인
```

계정 이름은 `~/.replydesk/accounts.json`에 적습니다(README의 "메일함이 여러 개일 때").
토큰은 기기마다 새로 받아야 합니다. 토큰 파일은 옮기지 마세요.

**주의**: Gmail 프로젝트가 테스트 모드면 사용할 계정이 **테스트 사용자로 등록돼 있어야** 합니다.
등록이 안 되면 동의 화면에서 403 access_denied 가 납니다(아래 결정 기록 참조).

## In progress

| Task | Who | Doing what | State | Started |
|---|---|---|---|---|
| — | — | 진행 중인 작업 없음 | — | — |

## For the user

| # | To do | Note |
|---|---|---|
| 1 | 실제 메일 30~50건 라벨 검수 | 판단 정확도 측정용. Claude가 초안을 달고 사람은 확인만 |
| 2 | 기업 CS 정책 한 장 (환불 규정·SLA·에스컬레이션 기준) | CS 질문 세트를 만들려면 필요 |

## Waiting on a decision

| Decision | Default if nothing is said | When |
|---|---|---|
| 다음 작업: 실제 메일 초안 만들기 vs 판단 정확도 측정 | 초안 만들기부터 (더 빨리 눈에 보임) | 2026-09-28 |
| 포트폴리오 증거 폴더를 저장소로 만들지 | 로컬 보관 (개인 대화 화면이 포함돼 있음) | 2026-09-28 |

---

## Log (newest first)

| Time | Kind | What happened | Result |
|---|---|---|---|
| 2026-09-28 07:05 | setup | 현황판 작성 | docs/progress.md, docs/state/active-work.json |
| 2026-09-28 06:55 | fix | Gmail 분당 할당량 초과 대응: 백오프·스캔 상한 | 두 메일함 34건 조회 성공 |
| 2026-09-28 06:40 | feat | 계정 이름 지정(`accounts.json`) | `--account yonsei` / `--account personal` |
| 2026-09-28 06:20 | feat | Gmail 채널(읽기·초안·발송) + 확인 절차 | 실제 메일함 20건 분류 확인 |
| 2026-09-28 05:30 | refactor | 임계값을 `THRESHOLDS` 한 표로, `route()` 추가 | 경계값 흔들림 문제 해결 |
| 2026-09-28 05:00 | feat | 최초 구현: 판단·초안·순위 파이프라인 + 샘플 받은편지함 | 저장소 공개 |

## Decisions (why — never rewritten)

| When | Decision | Why |
|---|---|---|
| 2026-09-28 | 원본 jev-chat-windows 코드를 복사하지 않고 새로 작성 | 배포 패키지가 GPLv3 UI 부품에 묶여 상업화 제약. 구조만 참고하고 출처는 README에 명시 |
| 2026-09-28 | 발송을 지원하되 파이프라인에서 분리 | 되돌릴 수 없는 유일한 동작. 사람이 `--send`를 붙이고 본문 확인 후 `send`를 입력해야 나감 |
| 2026-09-28 | Gmail 스팸·프로모션을 조회 단계에서 제외 | 이미 분류된 메일에 판단 비용을 쓸 이유가 없음. 가장 싼 필터가 가장 먼저 |
| 2026-09-28 | 개인 계정은 별도 Cloud 프로젝트 사용 | 학교 조직(yonsei.ac.kr)이 외부 테스터 등록 저장을 막음. 개인 계정 프로젝트는 제약 없음 |
| 2026-09-28 | `needs_human` 임계값 0.6 → 0.5 | 환불 건이 0.59/0.63 사이에서 흔들려 판정이 뒤집힘. 경계는 사람에게 넘기는 쪽으로 |
