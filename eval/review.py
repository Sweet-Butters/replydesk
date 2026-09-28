"""A local review screen for the gold labels.

    python -m eval.review          → http://127.0.0.1:8765

Runs on this machine only and writes straight to eval/data/gold.json. The sample is real private
correspondence, so it never goes to a hosted page: the reviewer's browser and the file on disk
are the whole system.

The model's answers are not served to this page. A reviewer who can see them is a reviewer who
agrees with them, and the whole measurement would be worth nothing.
"""
from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
GOLD = DATA / "gold.json"
PORT = 8765


def items() -> list[dict]:
    """Everything the reviewer needs, and nothing the judge said."""
    draft = {r["key"]: r for r in json.loads((DATA / "gold_draft.json").read_text(encoding="utf-8"))}
    saved = json.loads(GOLD.read_text(encoding="utf-8")) if GOLD.exists() else {}
    out = []
    for path in sorted((DATA / "threads").glob("*.json")):
        t = json.loads(path.read_text(encoding="utf-8"))
        d = draft.get(t["key"])
        if not d:
            continue
        out.append({
            "key": t["key"], "n": d["n"], "subject": t["subject"],
            "account": t["key"].split(":")[0],
            "replied_later": t.get("replied_later", False),
            "messages": [{"side": m["side"], "sender": m["sender"], "at": m["at"],
                          "text": m["text"][:4000]} for m in t["messages"][-6:]],
            "draft": d["draft"], "why": d["why"],
            "saved": saved.get(t["key"]),
        })
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/items"):
            self._send(200, json.dumps(items(), ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
        elif self.path in ("/", "/index.html"):
            self._send(200, (HERE / "review.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if not self.path.startswith("/save"):
            return self._send(404, b"not found", "text/plain")
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        saved = json.loads(GOLD.read_text(encoding="utf-8")) if GOLD.exists() else {}
        saved[payload["key"]] = payload["gold"]
        GOLD.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
        self._send(200, json.dumps({"saved": len(saved)}).encode(), "application/json")

    def log_message(self, *args) -> None:       # 검수 중에는 요청 로그가 방해만 됩니다
        pass


def main() -> None:
    print(f"검수 화면: http://127.0.0.1:{PORT}   (이 PC 밖으로 나가지 않습니다)")
    print(f"저장 위치: {GOLD}")
    print("끝내려면 Ctrl+C")
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    try:
        HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n중단했습니다. 저장된 검수 결과는 그대로 있습니다.")


if __name__ == "__main__":
    main()
