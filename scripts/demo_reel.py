"""Full DRY-RUN demo of the owner's reel flow (Task 04) on one water topic, in Uzbek.

Real: Claude research with web search + the research file, the 8-part Uzbek script, rubaiSTT transcription and
alignment, real licensed B-roll from Wikimedia Commons, the Remotion render `_v1`, the reel-mistakes checklist and the
section frames, the git commit into `reels/`, Buffer drafts and the story step (dry-run: recorded, not sent).
Stand-ins (clearly labelled): the owner's voice is an espeak-ng Uzbek TEST clip (tests/fixtures/sample_voice_demo_uz.wav);
the owner's cover is a plain TEST image; the owner's button presses are simulated; "the reel went live" is simulated
in the dry-run Buffer.

    PATH=$PWD/bin:$PATH systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue -- \
        .venv/bin/python scripts/demo_reel.py
Output: proof/reel/ (research, script, sources, export _v1.mp4, checklist, frames, Telegram messages).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from socialauto.app import build_app, reel_places  # noqa: E402
from socialauto.config import load_settings  # noqa: E402
from socialauto.logging_setup import setup_logging  # noqa: E402
from socialauto.reel import script as rs  # noqa: E402
from socialauto.telegram_bot import TelegramBot  # noqa: E402

PROOF = ROOT / "proof" / "reel"
DEMO = ROOT / "work" / "demo_reel"

spec = importlib.util.spec_from_file_location("demo_common", ROOT / "scripts" / "demo_common.py")
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


def prepare() -> Path:
    if DEMO.exists():
        shutil.rmtree(DEMO)
    DEMO.mkdir(parents=True)
    for name in ("assets", "models", "bin", "remotion"):
        (DEMO / name).symlink_to(ROOT / name)
    (DEMO / "docs").mkdir()
    cfg = (ROOT / "config.toml").read_text()
    cfg = cfg.replace('work_base = "~/MediaBuffer/_work"', f'work_base = "{DEMO}/MediaBuffer/_work"')
    cfg = cfg.replace('exports = "~/MediaBuffer/exports"', f'exports = "{DEMO}/MediaBuffer/exports"')
    cfg = cfg.replace('research_dir = "~/MediaBuffer/_work/research"', f'research_dir = "{DEMO}/MediaBuffer/_work/research"')
    (DEMO / "config.toml").write_text(cfg)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "demo@localhost"], ["config", "user.name", "Demo"]):
        subprocess.run(["git", "-C", str(DEMO), *args], check=True)
    (DEMO / ".gitignore").write_text("/data/\n/logs/\n/assets\n/models\n/bin\n/remotion\n/MediaBuffer/\n")
    subprocess.run(["git", "-C", str(DEMO), "add", ".gitignore", "config.toml"], check=True)
    subprocess.run(["git", "-C", str(DEMO), "commit", "-qm", "demo repo"], check=True)
    return DEMO


def test_cover(path: Path, title: str) -> Path:
    img = Image.new("RGB", (1080, 1920), (8, 47, 73))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(ROOT / "assets/fonts/Anton-Regular.ttf"), 110)
    small = ImageFont.truetype(str(ROOT / "assets/fonts/Montserrat-Bold.ttf"), 44)
    d.text((80, 700), "\n".join(title.upper()[i:i + 14] for i in range(0, min(len(title), 42), 14)), font=font, fill=(255, 255, 255))
    d.text((80, 1250), "TEST MUQOVA (egasi o'zi qiladi)", font=small, fill=(56, 189, 248))
    img.save(path, "PNG")
    return path


def main() -> int:
    PROOF.mkdir(parents=True, exist_ok=True)
    root = prepare()
    settings = load_settings(root / "config.toml", ROOT / ".env", root=root)
    settings = replace(settings, dry_run=True, allowed_user_ids=frozenset({1}),
                       buffer_api_key="", pexels_api_key="", pixabay_api_key="")
    setup_logging(settings.logs_dir)
    app = build_app(settings)
    tg = TelegramBot(app)
    rec = common.RecordingBot()
    tg.bot = rec

    wf = app.workflow
    log, t0 = [], time.time()

    def step(text: str) -> None:
        line = f"[{time.time() - t0:6.0f}s] {text}"
        print(line, flush=True)
        log.append(line)

    step(f"STT: {app.workflow.transcriber.__class__.__name__}")
    step("1. Research: Claude + web search (Buffer not connected in the demo)")
    rec.owner("/new")
    rec.reply(asyncio.run(tg.new_reply(None)))
    vid = app.store.videos()[0]["id"]
    common.run_jobs(app)
    asyncio.run(tg.deliver_outbox())
    reel = wf.reels.get(vid)
    step(f"   {len(reel['topics'])} topics; research file {Path(reel['research_file']).name}")
    token = app.store.pending_approval(vid, "topic")["id"]
    rec.owner(f"1. {reel['topics'][0]['title']}", "button")
    ok, msg = asyncio.run(tg.handle_button(1, f"t:0:{token}"))
    assert ok, msg
    rec.reply(msg)

    step("2. 8-part Uzbek script")
    from datetime import timedelta
    for attempt in range(4):                          # a failed draft is retried later, as the scheduler does
        common.run_jobs(app, now=app.clock() + timedelta(hours=2 * attempt))
        if app.store.video(vid)["status"] != "drafting":
            break
    asyncio.run(tg.deliver_outbox())
    script = app.store.script(vid)
    step(f"   '{script['title']}', ~{rs.estimated_seconds(script)}s, rule problems: {rs.problems(script)}")
    token = app.store.pending_approval(vid, "script")["id"]
    rec.owner("✅ Tasdiqlash", "button")
    ok, msg = asyncio.run(tg.handle_button(1, f"s:a:{token}"))
    assert ok, msg
    rec.reply(msg)
    asyncio.run(tg.deliver_outbox())

    step("3. Owner's voice = espeak-ng Uzbek TEST clip")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_test_voice_uz.py"), "demo_uz", rs.full_text(script)],
                   check=True, capture_output=True)
    sample = ROOT / "tests" / "fixtures" / "sample_voice_demo_uz.wav"
    ogg = root / "voice.ogg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(sample), "-c:a", "libopus", "-b:a", "48k", str(ogg)], check=True)

    async def dl(dest: Path) -> None:
        shutil.copyfile(ogg, dest)
    rec.owner("(ovozli xabar)", "voice")
    reply, markup = asyncio.run(tg.handle_upload("voice", ogg.stat().st_size, "audio/ogg", "", dl, user_id=1))
    rec.reply(reply, markup)

    step("4. rubaiSTT + alignment, real B-roll, Remotion render, checklist")
    common.run_jobs(app)
    video = app.store.video(vid)
    voice = app.store.voice(video["voice_id"])
    step(f"   voice {voice['duration']:.1f}s, coverage {voice['coverage']:.0%}; status {video['status']}")
    if video["status"] == "voice_check":                     # the robotic test voice: the owner says "continue"
        asyncio.run(tg.deliver_outbox())
        token = app.store.pending_approval(vid, "voice_check")["id"]
        rec.owner("▶️ Shu holicha davom et", "button")
        ok, msg = asyncio.run(tg.handle_button(1, f"c:k:{token}"))
        rec.reply(msg)
        if not ok:
            raise SystemExit(f"voice check refused: {msg}")
        common.run_jobs(app)
        video = app.store.video(vid)
    asyncio.run(tg.deliver_outbox())
    reel = wf.reels.get(vid)
    step(f"   status {video['status']}, version v{reel['version']}, checklist "
         f"{sum(c['ok'] for c in reel['checklist']['before']['checks'] + reel['checklist']['after']['checks'])}/"
         f"{len(reel['checklist']['before']['checks'] + reel['checklist']['after']['checks'])}")
    if video["status"] != "video_pending":
        raise SystemExit("render did not reach the owner's review")

    step("5. Owner approves -> cover -> git reels/ + Buffer drafts (dry-run)")
    token = app.store.pending_approval(vid, "video")["id"]
    rec.owner("✅ Tasdiqlash", "button")
    ok, msg = asyncio.run(tg.handle_button(1, f"v:a:{token}"))
    rec.reply(msg)
    asyncio.run(tg.deliver_outbox())
    cover = test_cover(root / "test_cover.png", script["title"])

    async def dl_cover(dest: Path) -> None:
        shutil.copyfile(cover, dest)
    rec.owner("(muqova rasmi)", "photo")
    rec.reply(asyncio.run(tg.handle_cover(dl_cover)))
    common.run_jobs(app)
    asyncio.run(tg.deliver_outbox())
    reel = wf.reels.get(vid)
    step(f"   git: {reel['git_note']}; drafts: {list(reel['drafts'])}")

    step("6. (simulated) the reel goes live in Buffer -> story step")
    wf.buffer.live.add(reel["drafts"]["instagram"])
    wf.tick()
    asyncio.run(tg.deliver_outbox())
    rec.owner("✅ Storyni joyladim", "button")
    ok, msg = asyncio.run(tg.handle_button(1, f"st:{vid}"))
    rec.reply(msg)
    step(f"   final status: {app.store.video(vid)['status']}")

    # --- proof ------------------------------------------------------------------------------------------------
    reel = wf.reels.get(vid)
    places = reel_places(settings)
    base, work = reel["base"], places.work(reel["base"])
    export = places.versions(base)[-1]
    shutil.copy(export, PROOF / export.name)
    shutil.copy(reel["research_file"], PROOF / Path(reel["research_file"]).name)
    for name in ("script.md", "SOURCES.md"):
        shutil.copy(work / name, PROOF / name)
    shutil.copy(work / "broll" / "sources.json", PROOF / "broll_sources.json")
    shutil.copy(work / f"checklist_v{reel['version']}.json", PROOF / f"checklist_v{reel['version']}.json")
    fdir = PROOF / "frames"
    if fdir.exists():
        shutil.rmtree(fdir)
    shutil.copytree(work / f"frames_v{reel['version']}", fdir)
    shutil.copy(settings.dryrun_posts_path, PROOF / "dryrun_posts.json")
    shutil.copy(root / "docs" / "reel-mistakes-checklist.md", PROOF / "reel-mistakes-checklist.md")
    git_log = subprocess.run(["git", "-C", str(root), "show", "--stat", "--format=%s", "HEAD"], capture_output=True, text=True).stdout
    (PROOF / "git_commit.txt").write_text(git_log, encoding="utf-8")
    (PROOF / "voice_alignment.json").write_text(json.dumps({"stt": app.workflow.transcriber.__class__.__name__,
                                                            "transcript": voice["transcript"], "coverage": voice["coverage"],
                                                            "duration": voice["duration"]}, indent=1, ensure_ascii=False))
    common.write_transcript(rec, PROOF / "telegram_messages.md")
    common.write_chat_html(rec, PROOF / "telegram_chat.html")
    (PROOF / "demo_log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    step(f"done: proof/reel/ ({export.name})")
    return 0 if app.store.video(vid)["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
