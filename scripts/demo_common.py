"""Helpers shared by the demo script: a recording stand-in for Telegram and the proof writers."""

from __future__ import annotations

import html
import re
import time
from pathlib import Path


class RecordingBot:
    """Stands in for Telegram's bot object: records every message exactly as it would be sent."""

    def __init__(self):
        self.messages: list[dict] = []

    @staticmethod
    def _buttons(markup):
        if not markup:
            return []
        return [[b.text for b in row] for row in markup.inline_keyboard]

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        self.messages.append({"from": "bot", "type": "text", "text": text, "buttons": self._buttons(reply_markup)})

    async def send_media_group(self, chat_id, media, **kw):
        self.messages.append({"from": "bot", "type": "photos", "captions": [m.caption for m in media]})

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kw):
        self.messages.append({"from": "bot", "type": "photo", "text": caption, "buttons": self._buttons(reply_markup),
                              "image": photo if isinstance(photo, (bytes, bytearray)) else None})

    async def send_video(self, chat_id, f, caption=None, reply_markup=None, **kw):
        self.messages.append({"from": "bot", "type": "video", "text": caption, "buttons": self._buttons(reply_markup),
                              "file": Path(f.name).name})

    def owner(self, text: str, kind: str = "text") -> None:
        self.messages.append({"from": "owner", "type": kind, "text": text})

    def reply(self, text: str, markup=None) -> None:
        self.messages.append({"from": "bot", "type": "text", "text": text, "buttons": self._buttons(markup)})


def run_jobs(app, now=None, limit=20) -> list[str]:
    ran = []
    for _ in range(limit):
        job = app.jobs.claim_next(now=(now or app.clock()).isoformat())
        if not job:
            break
        t = time.time()
        print(f"  job {job.kind} …", flush=True)
        app.workflow.run_job(job)
        print(f"  job {job.kind} done in {time.time() - t:.0f}s", flush=True)
        ran.append(job.kind)
    return ran


def tg_to_md(text: str) -> str:
    text = re.sub(r"</?b>", "**", text or "")
    text = re.sub(r"</?i>", "_", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def write_transcript(bot: RecordingBot, path: Path) -> None:
    out = ["# Telegram messages of the demo (exactly as the bot sends them)\n",
           "Recorded by the dry-run demo (`scripts/demo.py`). The real bot token is an owner step, so the messages were "
           "captured instead of sent; texts, buttons and media are identical.\n"]
    for m in bot.messages:
        who = "🤖 **Bot**" if m["from"] == "bot" else "👤 **Egasi (owner)**"
        out.append(f"\n---\n\n{who} — _{m['type']}_\n")
        if m["type"] == "photos":
            out.append("\n".join(f"- 🖼 {c}" for c in m["captions"]))
        else:
            if m["type"] == "video":
                out.append(f"🎬 *[video: {m['file']}]*\n")
            out.append(tg_to_md(m.get("text", "")))
        if m.get("buttons"):
            out.append("\n\nTugmalar: " + " · ".join(f"`[{b}]`" for row in m["buttons"] for b in row))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def write_chat_html(bot: RecordingBot, path: Path) -> None:
    """A Telegram-like rendering of the same messages (screenshotted for proof)."""
    rows = []
    for m in bot.messages:
        side = "me" if m["from"] == "owner" else "bot"
        if m["type"] == "photo" and m.get("image"):
            import base64
            uri = "data:image/jpeg;base64," + base64.b64encode(m["image"]).decode()
            m = dict(m, media=f'<img class="ph" src="{uri}">')
        body = m.get("text", "") or ""
        if m["from"] == "owner":
            body = html.escape(body)
        body = body.replace("\n", "<br>")
        media = m.get("media") or ('<div class="vid">▶ 1080×1920 video</div>' if m["type"] == "video" else "")
        if m["type"] in ("photo",) and m["from"] == "owner":
            media = '<div class="voice">🖼 (rasm)</div>'
        if m["type"] == "voice":
            media = '<div class="voice">🎙 ▮▮▯▮▮▮▯▮▯▮▮▯▮▮▮ 0:32</div>'
            body = ""
        btns = "".join('<div class="row">' + "".join(f"<span>{html.escape(b)}</span>" for b in row) + "</div>"
                       for row in m.get("buttons") or [])
        rows.append(f'<div class="msg {side}">{media}<div class="text">{body}</div>'
                    + (f'<div class="kb">{btns}</div>' if btns else "") + "</div>")
    css = """body{margin:0;background:#0e1621;font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#fff}
.head{position:sticky;top:0;background:#17212b;padding:14px 18px;font-weight:600;border-bottom:1px solid #0b121a}
.head small{display:block;color:#7f91a4;font-weight:400}.chat{max-width:560px;margin:0 auto;padding:16px 12px 40px}
.msg{max-width:88%;margin:8px 0;padding:9px 12px;border-radius:14px;background:#182533;word-wrap:break-word}
.msg.me{margin-left:auto;background:#2b5278}.text b{font-weight:700}.kb{margin-top:8px}.row{display:flex;gap:6px;margin-top:6px}
.row span{flex:1;text-align:center;background:#24394d;border-radius:8px;padding:8px 6px;font-size:13px;color:#cfe3ff}
.photos{display:flex;gap:6px;background:none;padding:0}.photos figure{margin:0;flex:1}.photos img{width:100%;border-radius:10px;display:block}
.photos figcaption{font-size:11px;color:#7f91a4;margin-top:4px}.vid{background:#000;border-radius:10px;height:160px;display:grid;place-items:center;color:#aaa;margin-bottom:8px}
.voice{color:#cfe3ff}.ph{width:100%;max-height:420px;object-fit:contain;border-radius:10px;margin-bottom:8px;background:#000}"""
    path.write_text(f"<!doctype html><meta charset=utf-8><style>{css}</style><div class=head>Social Automation bot"
                    f"<small>dry-run demo · recorded messages</small></div><div class=chat>{''.join(rows)}</div>",
                    encoding="utf-8")


