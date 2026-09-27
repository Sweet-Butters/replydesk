# KakaoTalk notes

KakaoTalk has no API for reading your own conversations, so the only input is the screen: capture
the chat window, OCR it, and work out who said what from bubble colour and position.

I already built that path, as a contribution to the desktop app this project's shape comes from:

- [jev-chat/jev-chat-windows#42](https://github.com/jev-chat/jev-chat-windows/pull/42) — Korean OCR
  (Windows.Media.Ocr instead of RapidOCR's zh/en models), per-app profiles, and skipping the pinned
  group notice that otherwise reads as a message.
- Measured on a live window: 0 of 9 bubbles read before, 9 of 9 after; 2.0 s → 0.20 s per frame;
  own messages correctly separated from the other side's.

Porting it here means writing a channel that produces `Thread` and `Message` from those OCR lines.
Two things to decide first:

1. **Where the reading happens.** The OCR path is Windows-only and needs the window on screen. That
   suits a desktop helper, not a server; a server-side deployment would need the person's machine to
   push threads to it.
2. **What leaves the machine.** OCR is local. The judgement call is not — the thread text goes to the
   decision model. For private chats that is a choice the user should make per conversation, not a
   default.
