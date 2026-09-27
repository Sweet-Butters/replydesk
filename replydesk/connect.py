"""One-time Gmail consent, run on its own so the URL is visible and the wait is generous.

    python -m replydesk.connect --account you@example.com

Prints the authorization URL before waiting, so it can be opened in whichever browser is already
signed in — including one on another machine, as long as the redirect lands back on this host.
The person approves; this only listens for the redirect and writes the token file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from .channels.gmail import SCOPES, _paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="replydesk.connect", description=__doc__)
    parser.add_argument("--account", default="", help="which mailbox, shown on the consent screen")
    parser.add_argument("--token", default="", help="where to write the token (default: env / beside credentials)")
    parser.add_argument("--no-browser", action="store_true", help="only print the URL, open it yourself")
    args = parser.parse_args(argv)

    creds_file, default_token = _paths()
    token_file = Path(args.token) if args.token else default_token
    if not creds_file.exists():
        print(f"OAuth 클라이언트 파일이 없습니다: {creds_file}\n"
              f"GMAIL_CREDENTIALS_FILE 로 경로를 지정하세요.", file=sys.stderr)
        return 2

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
    print(f"계정: {args.account or '(선택 화면에서 고르세요)'}")
    print(f"토큰 저장 위치: {token_file}")
    print("브라우저에서 동의하면 이 창이 저절로 끝납니다. 최대 10분 기다립니다.\n", flush=True)
    creds = flow.run_local_server(
        port=0,
        open_browser=not args.no_browser,
        login_hint=args.account or None,
        authorization_prompt_message="이 주소를 브라우저에서 여세요:\n{url}\n",
        success_message="연결됐습니다. 이 탭은 닫아도 됩니다.",
        timeout_seconds=600,
    )
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    print(f"\n토큰을 저장했습니다: {token_file}")
    print("권한:", ", ".join(s.rsplit('/', 1)[-1] for s in creds.scopes or SCOPES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
