# eval — 판단 정확도 측정

"잘 되는 것 같다"를 수치로 바꾸는 부분입니다. 외부 라이브러리 없이 돌아갑니다.

```bash
python -m eval.collect --want 25            # 받은편지함에서 표본 고정 저장 (중단돼도 이어받음)
python -m eval.collect --replied --want 12  # 실제로 답장한 메일을, 답장 직전 시점으로 되감아 추가
python -m eval.gold_draft                   # Claude의 블라인드 정답 초안
python -m eval.judge --repeat 3             # 판단 모델 실행 (자기일관성용 3회)
python -m eval.review                       # 사람이 검수 (이 PC에서만, http://127.0.0.1:8765)
python -m eval.metrics                      # 지표 계산 → data/results.json
```

## 순서가 규칙입니다

정답 초안은 **모델 답을 보기 전에** 답니다. 순서를 바꾸면 측정되는 것은 정확도가 아니라 동의율이
됩니다. 그래서 `gold_draft.py`는 예측 파일을 열지 않고, 검수 화면은 모델 답을 브라우저로 보내지
않습니다. 확인해 보려면:

```bash
grep -c predictions eval/gold_draft.py      # 0
curl -s localhost:8765/items | grep -c answers   # 0
```

## 개인정보

`eval/data/`는 git이 무시합니다. 받은 메일 전문이 들어 있고, 저장소에도 클라우드에도 올라가지
않습니다. 검수 화면은 127.0.0.1에만 묶이고 저장은 이 PC의 파일로 갑니다.

## 무엇을 재는가

| 파일 | 하는 일 |
|---|---|
| `collect.py` | 메일함 → `data/threads/*.json`. 같은 입력으로 두 번(사람·모델) 판단하기 위해 먼저 고정 |
| `gold_draft.py` | 55건의 블라인드 정답 초안. 근거 한 줄 포함 |
| `judge.py` | 판단 모델 실행 → `data/predictions.jsonl`. 반복 호출도 기록 |
| `review.py` + `review.html` | 로컬 검수 화면 → `data/gold.json` |
| `metrics.py` | 정확도·AUROC·PR-AUC·Brier·로그손실·ECE·신뢰도 곡선·층화 부트스트랩 95% CI·McNemar·자기일관성·선택적 예측·임계값 스윕 |
| `GUIDELINE.md` | 무엇을 정답이라 부를지. 측정 전에 고정 |

## 두 모집단을 섞지 않습니다

- `inboxOnly` — 받은편지함이 실제로 도착하는 모습. **운영 성능은 이 값입니다.**
- `all` — 여기에 "실제로 답장한 5건"을 더한 것. 양성이 6/55뿐이라 신뢰구간을 좁히려고 일부러
  더한 표본이고, 합치면 실제 메일함보다 양성 비율이 높아집니다.

## 지금 결과 (검수 전, 정답 = Claude 초안)

| 항목 | 값 |
|---|---|
| 표본 | 55건 (받은편지함 50 · 실제 답장 5), 계정 2개 |
| 건당 | 0.22초 · $0.000081 (입력 약 1,900토큰) |
| `needs_reply` | AUROC 0.9898 [0.9681, 1.0] · 임계값 0.5에서 정확도 0.855 · ECE 0.181 |
| 틀린 방향 | 위양성 8건, **놓친 답장 0건** |
| `action_elsewhere` | AUROC 0.6036 [0.4398, 0.7564] — 단독으로는 거의 무작위 |
| `urgency` | MAE 0.41 · ±1 안 87% · 순위상관 0.80 |
| 라우팅 | 정확도 0.800 [0.691, 0.891] |
| 규칙 기반 대조군 | 0.709 · McNemar p=0.039 |

검수가 끝나면 같은 명령이 그대로 다시 돌아 이 표를 갱신합니다.
