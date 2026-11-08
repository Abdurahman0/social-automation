"""Owner laws 15 and 16 as tests: the bot never publishes/uploads/schedules, and never makes a cover.

1. The package (and the scripts, the Remotion composition and the website) must not contain any publish / upload /
   schedule endpoint or method, nor a cover / thumbnail generator.
2. Every Buffer create call carries `saveToDraft: true`, with no way to turn it off and no due time.
"""

import ast
import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CODE = [p for d in ("socialauto", "scripts", "remotion/src") for p in (ROOT / d).rglob("*")
        if p.is_file() and p.suffix in (".py", ".ts", ".tsx", ".js", ".sh")]
FORBIDDEN = {
    r"videos\(\)\s*\.\s*insert|videos\.insert": "YouTube upload (videos.insert)",
    r"thumbnails\(\)\s*\.\s*set|thumbnails\.set": "YouTube custom thumbnail upload",
    r"MediaFileUpload": "YouTube media upload",
    r"youtube\.upload|youtube\.force-ssl|auth/youtube\"": "a YouTube write scope",
    r"media_publish": "Instagram media_publish",
    r"content_publishing_limit|instagram_content_publish": "Instagram publishing permission / limit",
    r"media_type\"?\s*[:=]\s*\"?(REELS|STORIES)": "an Instagram media container",
    r"shareNow|shareNext|customScheduled": "a Buffer share / schedule mode",
    r"\bdueAt\s*[\"']?\s*:": "a Buffer due time",
    r"saveToDraft\"?\s*:\s*False|saveToDraft\"?\s*=\s*False": "a non-draft Buffer post",
    r"post_now|publish_direct|retry_failed_post|\bPublisher\b|def book\(": "the removed direct-posting path",
    r"youtube_thumbnail|instagram_cover|make_thumbnail|thumbnails\.py|from \.+video import thumbnails": "a cover generator",
    r"image\.pollinations|PollinationsProvider": "AI image generation",
}


def scanned_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".py":           # docstrings/comments may explain the law; only code is checked
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return text
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
                        and isinstance(first.value.value, str):
                    first.value.value = ""
        text = ast.unparse(tree)
    return text


def without_legacy_cleanup(path: Path, text: str) -> str:
    """db.py may name the legacy posting columns in exactly one place: the migration that deletes them."""
    if path.name == "db.py":
        text = re.sub(r"def _remove_direct_posting\(.*?\n(?=\S)", "", text, flags=re.S)
    return text


@pytest.mark.parametrize("pattern,what", FORBIDDEN.items(), ids=list(FORBIDDEN.values()))
def test_no_publish_upload_schedule_or_cover_code(pattern, what):
    hits = [str(p.relative_to(ROOT)) for p in CODE if re.search(pattern, without_legacy_cleanup(p, scanned_text(p)))]
    assert not hits, f"{what} found in: {', '.join(hits)}"


def test_removed_modules_are_gone():
    for rel in ("socialauto/video/thumbnails.py", "socialauto/publishing", "socialauto/video/render.py",
                "socialauto/video/images.py", "socialauto/content.py"):
        assert not (ROOT / rel).exists(), rel


def test_every_buffer_create_is_a_draft():
    from socialauto.reel import buffer
    inp = buffer.draft_input("c", "t", "https://x/v.mp4", None, {"instagram": {"type": "reel", "shouldShareToFeed": True}})
    assert inp["saveToDraft"] is True and "dueAt" not in inp and inp["mode"] == "addToQueue"
    nasty = buffer.draft_input("c", "t", None, None, {"saveToDraft": False, "dueAt": "2030-01-01"})
    assert nasty["saveToDraft"] is True and "dueAt" not in nasty            # metadata cannot switch it off
    sig = inspect.signature(buffer.draft_input)
    assert not any(p in sig.parameters for p in ("save_to_draft", "draft", "due_at", "mode", "schedule"))
    # the only mutations in the module: createPost (drafts) and editPost (drafts only)
    src = Path(buffer.__file__).read_text()
    assert set(re.findall(r"mutation \w+\(\$input: (\w+)!\)", src)) == {"CreatePostInput", "EditPostInput"}
    assert "createPost(input: $input)" in src and "deletePost" not in src


def test_buffer_create_payload_over_http_is_a_draft(tmp_path):
    from socialauto.reel.buffer import GraphBuffer

    class HTTP:
        def __init__(self):
            self.calls = []
            self.answers = [{"data": {"account": {"organizations": [{"id": "o"}]}}},
                            {"data": {"channels": [{"id": "c", "service": "instagram"}]}},
                            {"data": {"createPost": {"post": {"id": "p", "text": "t", "status": "draft"}}}},
                            {"data": {"createPost": {"post": {"id": "s", "text": "t", "status": "draft"}}}}]

        def post(self, url, json=None, headers=None, timeout=None):
            self.calls.append(json)
            body = self.answers.pop(0)

            class R:
                status_code = 200

                def json(self_inner):
                    return body
            return R()
    http = HTTP()
    b = GraphBuffer("k", session=http)
    ch = b.channels()[0]
    b.create_draft(ch, "reel", "https://x/v.mp4", None, {"instagram": {"type": "reel", "shouldShareToFeed": True}})
    b.create_draft(ch, "story", None, "https://x/c.jpg", {"instagram": {"type": "story", "shouldShareToFeed": False}},
                   reminder=True)
    creates = [c["variables"]["input"] for c in http.calls if "createPost" in c["query"]]
    assert len(creates) == 2 and all(i["saveToDraft"] is True and "dueAt" not in i for i in creates)


def test_buffer_edits_only_drafts(tmp_path):
    from socialauto.platforms.dryrun import DryRunLog
    from socialauto.reel.buffer import BufferError, DryRunBuffer
    b = DryRunBuffer(DryRunLog(tmp_path / "d.json"))
    pid = b.create_draft({"id": "c", "service": "youtube"}, "t", "v", None, {})
    b.edit_post(pid, text="new")
    b.live.add(pid)
    with pytest.raises(BufferError):
        b.edit_post(pid, text="after it went live")


def test_old_database_loses_the_posting_tables(tmp_path):
    import sqlite3
    from socialauto import db as dbmod
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""CREATE TABLE videos (id INTEGER PRIMARY KEY, status TEXT, post_now INTEGER, announced_at TEXT);
        CREATE TABLE approvals (id TEXT PRIMARY KEY, post_now INTEGER);
        CREATE TABLE renders (id INTEGER PRIMARY KEY, thumb_youtube TEXT, cover_instagram TEXT);
        CREATE TABLE posts (id INTEGER PRIMARY KEY); CREATE TABLE post_events (id INTEGER PRIMARY KEY);
        CREATE TABLE reels (video_id INTEGER PRIMARY KEY); INSERT INTO videos VALUES (1, 'posted', 0, NULL);""")
    dbmod._remove_direct_posting(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "posts" not in tables and "post_events" not in tables
    assert {r[1] for r in conn.execute("PRAGMA table_info(renders)")} == {"id"}
    assert conn.execute("SELECT status FROM videos").fetchone()[0] == "done"
    dbmod._remove_direct_posting(conn)                                        # idempotent
