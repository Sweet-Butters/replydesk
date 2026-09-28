"""Claude's blind draft of the gold labels, written before the judge was ever run.

The order matters and is the point: these values were decided from the mail alone, with no
model answer on screen. Running the judge first and labelling afterwards would measure
agreement with the judge, not accuracy.

A person reviews every row afterwards (see GUIDELINE.md); their answer is the gold label.
This file is only the starting draft — and the rows where the two disagree are reported, not
quietly resolved.

표본 자체(메일 본문)는 공개되지 않습니다. 근거 줄은 무엇을 보고 그렇게 판단했는지를 남기되,
남의 메일 문장을 인용하지 않고 종류만 적습니다.

Values: needs_reply / action_elsewhere / needs_human as True, False or None ("판단 보류"),
urgency 0-3 as defined in the guideline. `why` is one line, so a reviewer can see what the
draft was reasoning from.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

# (순번, needs_reply, action_elsewhere, needs_human, urgency, 한 줄 근거)
DRAFT = [
    (1,  False, False, None, 0, "ChatGPT 뉴스레터 — 활용 사례 소개"),
    (2,  False, False, None, 0, "Reddit 주제 알림"),
    (3,  False, False, None, 1, "GitHub OAuth 앱 추가 알림 — 본인이면 조치 없음"),
    (4,  False, True,  None, 1, "수강 시작 안내, 발신전용 — 학습은 별도 사이트에서"),
    (5,  False, True,  None, 1, "GitHub Actions 실패 알림 — 할 일은 저장소 수정"),
    (6,  False, True,  None, 3, "Meta 인증번호 — 입력해야 하고 곧 만료"),
    (7,  False, False, None, 0, "대기 명단 등록 완료 통보"),
    (8,  False, False, None, 0, "Reddit 주제 알림"),
    (9,  False, False, None, 0, "약관 변경 안내"),
    (10, False, True,  None, 1, "GitHub Actions 실패 알림"),
    (11, False, False, None, 0, "구글 로그인 데이터 공유 알림 — 조치 불필요 명시"),
    (12, False, False, None, 0, "Reddit 주제 알림"),
    (13, False, True,  None, 1, "GitHub Actions 실패 알림"),
    (14, False, True,  None, 2, "도메인 연락처 확인 요구 — 링크에서 처리, 미이행 시 정지"),
    (15, False, True,  None, 3, "이메일 인증번호 — 입력해야 하고 곧 만료"),
    (16, False, False, None, 0, "회원가입 완료 통보"),
    (17, False, False, None, 0, "Reddit 주제 알림"),
    (18, False, False, None, 1, "GitHub OAuth 앱 추가 알림"),
    (19, False, False, None, 2, "낯선 기기 로그인 알림 — 본인 확인 필요"),
    (20, False, True,  None, 1, "GitHub Actions 실패 알림"),
    (21, False, True,  None, 1, "무료 체험 만료 — 30일 안에 업그레이드 또는 데이터 회수"),
    (22, False, False, None, 0, "구글 로그인 데이터 공유 알림"),
    (23, False, True,  None, 1, "공개 저장소 코드 리뷰 알림 — 할 일은 저장소에서, 답을 기다리진 않음"),
    (24, False, False, None, 0, "Reddit 주제 알림"),
    (25, False, False, None, 0, "구글 로그인 데이터 공유 알림"),
    (26, True,  True,  False, 2, "담당자가 처리 여부를 직접 물음 — 포털 입력 + 확인 회신"),
    (27, True,  False, True,  2, "선발 통보 — 참석 가능한 시간을 기한까지 회신하라고 요구"),
    (28, True,  False, True,  3, "일정 조율 — 당일 몇 시간 안에 회신하라고 명시"),
    (29, True,  False, False, 2, "내가 보낸 요청에 상대가 되물음 — 사실 확인 답변"),
    (30, True,  True,  False, 3, "참가 확정 통보 + 며칠 뒤 필수 일정, 준비물 있음"),
    (31, False, False, None, 0, "DBpia 주간 추천 뉴스레터"),
    (32, False, False, None, 0, "대학원 신입생 모집 공지"),
    (33, False, True,  None, 1, "참가자 모집 — 구글폼으로 신청"),
    (34, False, False, None, 0, "행사 예고 티저"),
    (35, True,  False, True,  1, "기한을 정해 산출물 회신을 요구 — 내가 만든 결과물 제출"),
    (36, False, True,  None, 1, "포럼 참가 신청 안내"),
    (37, False, False, None, 0, "대학원 신입생 모집 공지"),
    (38, False, False, None, 0, "대학원 모집 + 설명회 안내"),
    (39, False, False, None, 0, "제품 업데이트 뉴스레터"),
    (40, False, False, None, 0, "입학설명회 공지"),
    (41, False, False, None, 1, "구글 새 로그인 보안 알림 — 본인이면 조치 없음"),
    (42, False, False, None, 1, "교내 행사 안내 — 며칠 뒤, 신청 언급 없음"),
    (43, False, False, None, 0, "입학설명회 공지"),
    (44, False, False, None, 0, "예배 안내"),
    (45, False, False, None, 0, "대학원 신입생 모집 공지"),
    (46, False, True,  None, 3, "신청 링크 — 마감이 수신 당일 자정"),
    (47, False, True,  None, 1, "콜로퀴엄 참가 신청 — 선착순"),
    (48, False, False, None, 0, "대학원 신입생 모집 공지"),
    (49, False, False, None, 0, "학교 소식지"),
    (50, False, True,  None, 3, "지원서 인증번호 — 입력해야 진행"),
    (51, False, False, None, 0, "지원 접수 완료 통보"),
    (52, False, True,  None, 2, "며칠 뒤 공개강연 — 참석 신청을 받는 중"),
    (53, False, False, None, 0, "대학원 신입생 모집 공지"),
    (54, False, False, None, 2, "며칠 뒤 세미나 — 회신은 조건부(동반자·불참 시에만)"),
    (55, False, False, None, 0, "대학원 신입생 모집 공지"),
]


def main() -> None:
    paths = sorted((DATA / "threads").glob("*.json"))
    if len(paths) != len(DRAFT):
        raise SystemExit(f"스레드 {len(paths)}건인데 초안은 {len(DRAFT)}건 — 순서가 어긋납니다")
    rows = []
    for path, row in zip(paths, DRAFT):
        thread = json.loads(path.read_text(encoding="utf-8"))
        n, reply, elsewhere, human, urgency, why = row
        rows.append({
            "n": n,
            "key": thread["key"],
            "subject": thread["subject"],           # 검수 화면에서 같은 메일인지 확인용
            "replied_later": thread.get("replied_later", False),
            "draft": {"needs_reply": reply, "action_elsewhere": elsewhere,
                      "needs_human": human, "urgency": urgency},
            "why": why,
        })
    out = DATA / "gold_draft.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    yes = sum(r["draft"]["needs_reply"] for r in rows)
    behaved = sum(r["replied_later"] for r in rows)
    print(f"{len(rows)}건 저장 → {out}")
    print(f"  답장 필요 {yes}건 ({yes / len(rows):.0%}) · 실제로 답장한 기록 {behaved}건")
    agree = sum(r["draft"]["needs_reply"] for r in rows if r["replied_later"])
    print(f"  실제 답장한 {behaved}건 중 초안도 '답장 필요'로 본 것 {agree}건")


if __name__ == "__main__":
    main()
