"""A fixed inbox, so the pipeline runs before any mailbox is connected.

These are written to cover the cases the questions exist to separate: a blocked customer, a polite
nudge on a promise we broke, a newsletter that needs no reply, and a refund demand that a person
should answer personally.
"""
from __future__ import annotations

import datetime as dt

from ..models import Message, Thread

_NOW = dt.datetime(2026, 9, 28, 9, 30)


def _at(minutes: int) -> dt.datetime:
    return _NOW - dt.timedelta(minutes=minutes)


THREADS: list[Thread] = [
    Thread(
        id="t1", channel="email", subject="결제가 안 됩니다 (주문 A-2291)",
        context={"plan": "비즈니스", "order": "A-2291", "status": "결제 실패 3회"},
        messages=(
            Message("them", "어제부터 결제가 계속 실패합니다. 카드는 정상인데 3번이나 막혔어요. "
                            "오늘 오후까지 처리 못 하면 다른 데 알아봐야 할 것 같습니다.",
                    sender="김민수", at=_at(35)),
        ),
    ),
    Thread(
        id="t2", channel="email", subject="Re: 견적서 회신 부탁드립니다",
        context={"account": "누리테크", "stage": "견적 검토"},
        messages=(
            Message("them", "안녕하세요, 지난주에 요청드린 견적서 회신 가능하실까요?", sender="이정현", at=_at(60 * 72)),
            Message("us", "네, 내일까지 정리해서 보내드리겠습니다.", at=_at(60 * 71)),
            Message("them", "혹시 오늘 중으로 받아볼 수 있을까요? 내부 보고가 내일 오전이라서요.",
                    sender="이정현", at=_at(90)),
        ),
    ),
    Thread(
        id="t3", channel="email", subject="[뉴스레터] 9월 제품 업데이트",
        messages=(
            Message("them", "이번 달 업데이트 소식을 전해드립니다. 새로운 대시보드가 추가되었습니다. "
                            "수신을 원하지 않으시면 하단에서 해지하실 수 있습니다.",
                    sender="프로덕트팀", at=_at(60 * 5)),
        ),
    ),
    Thread(
        id="t4", channel="email", subject="환불 요청합니다",
        context={"plan": "프로", "billed": "2026-09-03", "refund_policy": "7일 이내 전액, 이후 일할 계산"},
        messages=(
            Message("them", "9월 3일에 결제했는데 기능이 설명과 다릅니다. 전액 환불해 주세요. "
                            "안 되면 카드사에 이의제기하겠습니다.", sender="박지훈", at=_at(20)),
        ),
    ),
]


class SampleChannel:
    name = "sample"

    def fetch(self, limit: int = 20) -> list[Thread]:
        return THREADS[:limit]

    def stage(self, thread: Thread, text: str) -> str:
        raise NotImplementedError("the sample inbox has nowhere to stage a reply")
