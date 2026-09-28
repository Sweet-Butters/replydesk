"""Send a summary to the person's own KakaoTalk, through Kakao's "메모" (note-to-self) API.

    python -m replydesk.notify.kakao            # one-time consent
    python -m replydesk.notify.kakao --test     # send a test line

This is deliberately the weakest thing KakaoTalk offers, and that is why it is safe to wire in.
Kakao has no API that reads a personal chat, and sending to anyone else needs a reviewed business
app — so this channel can only ever write one message, to the account holder, in their own
note-to-self room. A bug here cannot reach another person.

It is a *notifier*, not a channel: nothing in the judge-write-rank pipeline can call it, the same
way nothing there can reach Gmail's send(). The digest command calls it after a person asked for
a digest.

Setup, once (about 3 minutes):
  1. https://developers.kakao.com/console/app → 애플리케이션 추가하기
  2. 앱 설정 → 플랫폼 → Web 플랫폼 등록: http://localhost:8123
  3. 제품 설정 → 카카오 로그인 → 활성화 ON, Redirect URI: http://localhost:8123/oauth
  4. 제품 설정 → 카카오 로그인 → 동의항목 → "카카오톡 메시지 전송"(talk_message) 사용 설정
  5. 앱 키의 REST API 키를 KAKAO_REST_API_KEY (또는 ..._FILE) 로 지정
Sending to yourself needs no business review; sending to friends does, and this never does that.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .. import config

AUTH = "https://kauth.kakao.com/oauth/authorize"
TOKEN = "https://kauth.kakao.com/oauth/token"
MEMO = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
SCOPE = "talk_message"
PORT = 8123
REDIRECT = f"http://localhost:{PORT}/oauth"
LIMIT = 200          # Kakao's text template caps the body at 200 characters, and truncates silently


def token_path() -> Path:
    return Path.home() / ".replydesk" / "kakao_token.json"


def _post(url: str, form: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=body, headers=headers or {})
    req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


class _Catch(BaseHTTPRequestHandler):
    """Catches the one redirect the consent screen sends back. It never sees a password."""

    code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Catch.code = (query.get("code") or [None])[0]
        _Catch.error = (query.get("error_description") or query.get("error") or [None])[0]
        done = "동의가 끝났습니다. 이 창을 닫으셔도 됩니다." if _Catch.code else \
               f"동의를 받지 못했습니다: {_Catch.error}"
        page = f"<!doctype html><meta charset=utf-8><body style='font:16px system-ui;padding:40px'>{done}"
        body = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def connect(open_browser: bool = True) -> Path:
    """Run the one-time consent and write the token file. The person approves; we only listen."""
    client_id = config.key("KAKAO_REST_API_KEY")
    url = f"{AUTH}?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT,
        "response_type": "code", "scope": SCOPE})
    print("아래 주소에서 동의해 주세요. 카카오 계정으로 로그인된 브라우저면 됩니다.\n")
    print(url + "\n", flush=True)
    if open_browser:
        webbrowser.open(url)
    server = HTTPServer(("127.0.0.1", PORT), _Catch)
    server.timeout = 300
    while _Catch.code is None and _Catch.error is None:
        server.handle_request()
    if not _Catch.code:
        raise RuntimeError(f"동의를 받지 못했습니다: {_Catch.error}")

    token = _post(TOKEN, {"grant_type": "authorization_code", "client_id": client_id,
                          "redirect_uri": REDIRECT, "code": _Catch.code})
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _access_token() -> str:
    """The stored token, refreshed when Kakao says it has expired."""
    path = token_path()
    if not path.exists():
        raise RuntimeError("카카오 연결이 없습니다. python -m replydesk.notify.kakao 를 먼저 실행하세요")
    token = json.loads(path.read_text(encoding="utf-8"))
    return token["access_token"]


def _refresh() -> str:
    path = token_path()
    token = json.loads(path.read_text(encoding="utf-8"))
    if not token.get("refresh_token"):
        raise RuntimeError("갱신 토큰이 없습니다. python -m replydesk.notify.kakao 로 다시 연결하세요")
    fresh = _post(TOKEN, {"grant_type": "refresh_token",
                          "client_id": config.key("KAKAO_REST_API_KEY"),
                          "refresh_token": token["refresh_token"]})
    token.update({k: v for k, v in fresh.items() if v})   # Kakao omits refresh_token when it is still valid
    path.write_text(json.dumps(token, ensure_ascii=False, indent=1), encoding="utf-8")
    return token["access_token"]


def send(text: str, link: str = "") -> str:
    """Put one message in the person's own note-to-self room. Never reaches anyone else."""
    if len(text) > LIMIT:
        text = text[:LIMIT - 1].rstrip() + "…"            # Kakao truncates silently; be explicit
    template = {"object_type": "text", "text": text,
                "link": {"web_url": link, "mobile_web_url": link} if link else {}}
    form = {"template_object": json.dumps(template, ensure_ascii=False)}
    try:
        _post(MEMO, form, {"Authorization": f"Bearer {_access_token()}"})
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError(f"카카오 전송 실패 ({exc.code}): {exc.read().decode('utf-8')[:200]}") from exc
        _post(MEMO, form, {"Authorization": f"Bearer {_refresh()}"})
    return "카카오톡 '나와의 채팅'으로 보냈습니다"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="replydesk.notify.kakao", description=__doc__.split("\n\n")[0])
    ap.add_argument("--test", action="store_true", help="연결을 확인하는 한 줄을 보냅니다")
    ap.add_argument("--no-browser", action="store_true", help="주소만 출력하고 직접 여세요")
    args = ap.parse_args(argv)
    try:
        if args.test:
            print(send("replydesk 연결 확인 — 이 메시지가 보이면 알림이 동작합니다."))
            return 0
        print(f"토큰을 저장했습니다 → {connect(open_browser=not args.no_browser)}")
        print("확인: python -m replydesk.notify.kakao --test")
    except (config.MissingKey, RuntimeError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
