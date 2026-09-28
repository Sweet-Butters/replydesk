# replydesk

English: [README.md](README.md)

**쓰기 전에 판단하는** 답장 도우미입니다. 사람이 책임지고 답해야 하는 받은편지함을 위한 도구예요.
지금은 이메일, 다음은 채팅과 고객 문의 큐입니다.

대부분의 도구는 대화를 통째로 언어 모델에 넘기고 답장을 받아옵니다. 이 도구는 먼저 판단 모델에게
일곱 가지를 묻습니다. 답장이 필요한가, 무엇을 원하는가, 얼마나 급한가, 얼마나 화가 났는가,
지금 있는 정보로 답할 수 있는가, 사람이 직접 써야 하는가, 우리가 한 약속이 남아 있는가.
그 답에 맞춰 초안 세 개를 쓰고, 사람이 하나를 골라 고쳐서 보냅니다.

```
                    ┌──────────── 판단 (Jev) ─────────────┐
 대화 ────────────► │ 답장 필요        0.95               │
 (채널 무관)         │ 원하는 것        처리 요청 (0.37)    │──► 지침 ──┐
                    │ 긴급도          2.3 / 3             │           │
                    │ 불만도          2.3 / 3             │           ▼
                    │ 여기서 답 가능    0.31               │     작성 (Gemini)
                    │ 사람이 직접      0.26               │      초안 3개
                    │ 남은 약속        0.06               │           │
                    └────────────────────────────────────┘           ▼
                                                           순위 (Jev) ──► 사람이 발송
```

## 왜 앞부분을 판단 모델에 맡기나

`의도 = 결제·청구, 확신 0.93`은 코드가 분기할 수 있는 값입니다. 줄글 설명은 그렇지 않습니다.
확신이 낮다는 것도 실패가 아니라 "사람에게 넘겨라"라는 신호입니다. 그리고 판단은 싸서
(입력 약 1,900토큰, 건당 약 0.00008달러) 받은편지함 전체에 돌릴 수 있는 반면, 비싼 쪽인 초안 작성은
사람이 실제로 답하려는 메일에만 돌립니다.

샘플 받은편지함 기준으로 판단만 하면 건당 0.4초, 판단 + 초안 3개 + 순위까지 2.2초입니다.

## 빠른 시작

```bash
pip install -e .
export TYPESAFE_API_KEY=...        # 또는 TYPESAFE_API_KEY_FILE=/키/파일/경로
export GEMINI_API_KEY=...          # 또는 GEMINI_API_KEY_FILE=/키/파일/경로

python -m replydesk triage         # 답장 기다리는 메일을 전부 판단해 한 줄씩
python -m replydesk reply t1       # 한 건을 판단하고 초안 3개를 쓰고 순위를 매김
python -m replydesk reply t1 --json
```

메일함을 연결하기 전에도 샘플 받은편지함으로 전체 흐름을 볼 수 있습니다. 키는 환경변수나
환경변수가 가리키는 파일에서만 읽고, 저장소에 들어가지 않으며 로그에도 남지 않습니다.

## 분류 결과 예시

```
[t1] 긴급 2.3/3 · 처리 요청 · 초안 가능  · 결제가 안 됩니다 (주문 A-2291)
[t2] 긴급 2.0/3 · 처리 요청 · 초안 가능  · Re: 견적서 회신 부탁드립니다
[t3] 긴급 0.0/3 · 기타      · 초안 가능  · [뉴스레터] 9월 제품 업데이트
[t4] 긴급 2.1/3 · 처리 요청 · 사람이 직접 · 환불 요청합니다
```

환불 요구는 스스로 "사람이 직접"으로 빠지고, 뉴스레터는 긴급도 0.0이라 초안 모델까지 가지 않습니다.

## 채널 추가하기

채널이 하는 일은 자기 데이터를 `Thread`와 `Message`(`replydesk/models.py`)로 바꾸는 것,
그리고 가능하면 고른 초안을 사람이 보낼 자리에 넣어 두는 것뿐입니다. 그 위는 채널과 무관합니다.

| 채널 | 입력 | 상태 |
|---|---|---|
| 샘플 받은편지함 | 고정 데이터 | 동작 |
| 이메일 | Gmail API | 동작 — 읽기·초안·발송 |
| 고객 문의 큐 | 헬프데스크 API | 예정 |
| 커뮤니티·SNS 댓글 | 플랫폼 API | 예정 — 각 플랫폼 약관 확인 필요 |
| 카카오톡 | 화면 캡처 + OCR (API 없음) | 예정, [메모](docs/kakaotalk.md) |

질문 세트는 채널 옆에 둡니다(`replydesk/questions/`). 이메일은 긴급도와 남은 약속을 묻고,
고객 문의 큐라면 환불 권한과 SLA를, 댓글이라면 답할 가치가 있는지를 묻게 됩니다. 파이프라인은
그대로입니다.

## Gmail 연결

```bash
pip install -e ".[gmail]"
export GMAIL_CREDENTIALS_FILE=/경로/credentials.json   # 데스크톱 OAuth 클라이언트
export GMAIL_TOKEN_FILE=/경로/token.json               # 메일함마다 하나
python -m replydesk.connect --account you@example.com  # 최초 1회 동의, 브라우저에서

python -m replydesk triage --channel gmail
python -m replydesk reply <스레드 id> --channel gmail --stage   # 임시보관함에 초안으로
python -m replydesk reply <스레드 id> --channel gmail --send    # 보여준 뒤 확인을 묻고 발송
```

### 메일함이 여러 개일 때

`~/.replydesk/accounts.json`(또는 `REPLYDESK_ACCOUNTS`가 가리키는 파일)에 한 번 적어 두면
명령줄에서 경로를 넘기지 않아도 됩니다. 이 파일에는 경로와 조회 조건만 들어가고 키나 토큰은
들어가지 않습니다.

```json
{
  "work":     {"channel": "gmail", "email": "me@company.com",
               "credentials": "/keys/client.json", "token": "/keys/work.json"},
  "personal": {"channel": "gmail", "email": "me@gmail.com",
               "credentials": "/keys/client_personal.json", "token": "/keys/personal.json",
               "query": "in:inbox newer_than:7d"}
}
```

```bash
python -m replydesk triage --channel gmail --account work
```

권한은 `gmail.readonly`, `gmail.compose`, `gmail.send` 세 개입니다. 스팸·프로모션·소셜·포럼은
조회에서 빼기 때문에, Gmail이 이미 한 분류가 공짜 1차 필터가 됩니다.

## 요약을 폰으로 받기

`digest` 는 대기 중인 스레드를 전부 판단해서 폰 크기의 요약 한 덩어리를 출력합니다. 분류별 건수
다음에, 사람이 손대야 하는 건을 급한 순서로 보여줍니다.

```
[replydesk] 9/29 메일 40건
답장 4 · 폼·링크 3
🔴 [참석 안내] 9/30(수) 스타트업 성장 세미나
· Re: 견적서 회신 부탁드립니다
```

이걸 카카오톡 '나와의 채팅'으로 보낼 수 있습니다.

```bash
python -m replydesk.notify.kakao                 # 최초 1회 동의
python -m replydesk digest --channel gmail --account work,personal --notify kakao
```

카카오 메모 API를 씁니다. **이걸 고른 이유가 곧 안전장치입니다** — 카카오에는 개인 대화를 읽는
API가 없고, 남에게 메시지를 보내려면 심사받은 비즈니스 앱이 필요합니다. 이 알림은 계정 주인의
나와의 채팅방에 메시지 하나를 쓰는 것밖에 못 합니다. 채널이 아니라 알림이라서, 판단·작성·순위
파이프라인에서는 닿을 수 없고 다른 사람을 수신자로 삼을 수도 없습니다.

준비물은 카카오 디벨로퍼스 앱 하나입니다. **단계별 안내는 [docs/kakao-setup.md](docs/kakao-setup.md)** 에 있습니다 — 실제로 막혔던 지점(포트가 붙은 도메인은 거부됨, Redirect URI 칸은 로그인을 켜야 보임)까지 그대로 적어 뒀습니다. 카카오 로그인 활성화, 동의항목 `talk_message` 사용,
Redirect URI 에 `http://localhost:8123/oauth` 등록, 그리고 REST API 키를 `KAKAO_REST_API_KEY`
(또는 `KAKAO_REST_API_KEY_FILE`) 로 지정하면 됩니다. 요약에 담긴 **제목은 카카오 서버로 나갑니다** —
그게 곤란하면 `--notify` 없이 `digest` 만 쓰세요.

## 요약에 답장해서 시키기

카카오톡은 단방향입니다 — 나와의 채팅방에 뭘 써도 읽을 수 없습니다. 그래서 **시키는 쪽은 메일**
입니다. `--mail` 을 붙이면 요약이 본인 메일로도 오고, 손댈 수 있는 스레드마다 번호가 붙습니다.
그 메일에 답장하는 게 곧 지시입니다.

```
2번 초안          → 2번 메일의 답장 초안을 임시보관함에 넣습니다
2, 5번 초안       → 여러 건을 한 번에
3번 건너뛰기      → 처리한 것으로 표시하고 다음 요약에서 뺍니다
전체 건너뛰기     → 목록을 비웁니다
```

```bash
python -m replydesk digest --channel gmail --account work,personal --notify kakao --mail
python -m replydesk commands --channel gmail     # 답장을 읽고 실행합니다
```

메일함이 명령 채널이어도 안전한 이유는 두 가지입니다.

- **우리가 보낸 요약에 달린 답장만 읽습니다.** 메일함을 명령어로 검색하지 않고, 이 프로그램이
  만든 스레드에서 **우리 메시지 이후**만 읽습니다. 남이 보낸 메일은 그 스레드에 없으므로 지시가
  될 수 없습니다.
- **동사 집합이 닫혀 있고, 발송이 없습니다.** 답장으로 일어날 수 있는 최대치는 내 임시보관함에
  초안이 생기는 것입니다. 발송은 여전히 `--send` 와 터미널에서 직접 입력하는 확인이 필요합니다.

못 알아들은 줄은 추측하지 않고 무시하며, 무엇을 알아들었는지 실행할 때 출력합니다.

## 하지 않는 것

- **스스로 보내지 않습니다.** 파이프라인에서는 발송 함수에 닿을 수 없습니다. 사람이 `--send`를 붙이고,
  받는 사람·제목·본문을 확인한 뒤 `send`라고 입력해야 나갑니다. 판단이 "사람이 직접"으로 분류한
  메일은 `--force` 없이는 거부합니다.
- **없는 사실을 지어내지 않습니다.** 대화에 없는 날짜·금액·정책을 쓰지 못하게 막았습니다. 확인이
  필요하면 "무엇을 언제까지 확인하겠다"고 쓰게 합니다.
- **메일의 지시를 따르지 않습니다.** 대화 안의 명령처럼 보이는 문장은 지시가 아니라 상대가 보낸
  내용으로 취급합니다.

## 출처

판단 → 작성 → 순위라는 구조는 [jev-chat-windows](https://github.com/jev-chat/jev-chat-windows)(MIT)의
것입니다. 저는 그 저장소에 한국어 지원을 기여했습니다. 코드는 가져오지 않았습니다. 이 저장소는
API 기반 채널을 위해 새로 작성했고 GUI 의존성이 없습니다.

판단은 [TypeSafe Jev](https://docs.typesafe.ai/), 초안은 Gemini를 씁니다. 라이선스는 MIT입니다.
