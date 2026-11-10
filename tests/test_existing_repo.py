"""Task 09: a user connects his EXISTING content repo (first user: Javohir, `the-suvyektiv-media`).

Every test works on LOCAL bare repos shaped like his (reels/<date>-<topic>/reel.mp4 + cover.jpg + script.md,
posted.md, brand/, .claude/skills/, posts/, audits/). The real GitHub repo is never touched. Set SA_SUV_BARE to a
local bare copy of his real repo to also run the last test against his real history.
"""

import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from socialauto.content_repo import (NOTE_CONFLICT, PENDING_PREFIX, ContentPushRefused, ContentRepo, parse_repo_ref)

POSTED = """# Posted log

YYYY-MM-DD | pillar | topic | hook | CTA#

2026-10-15 | REEL | Suv tozalash usullari 2-qism: Biologik tozalash | Bakteriya haqida eshitganimizda… | -
2026-10-21 | 3 Suvni isrof qilmaslik | Tomchilayotgan kran | Bitta tomchi hech narsa emas. | 2
2026-11-04 | 2 Research paper | Butilka suvdagi nanoplastik | 1 litr butilka suvda 240 mingta plastik zarra. | 1
"""
VOICE = """# voice.md — Doktor H₂O (@suvyektiv)
- **Uzunlik (audit 28.10):** reel 30–40 s, maksimum 45 s (~90–100 so'z).
- **Brand line / CTA:** "Suvni qadrlang! ... suv haqida suvyektiv fikrlaymiz!"
- Raqam, statistika yoki iqtibosni o'ylab topmaslik — faqat manbada bor narsa.
"""
SCRIPT_MD = """# 5 ta suv tejash layfhagi

## Ovoz matni (subtitr bilan bir xil)
1. (5.5 s) 5 ta oddiy odat bilan bir yilda o'n minglab litr suvni tejash mumkin.
2. (7.5 s) Birinchisi: tish yuvayotganda kranni yoping.
"""


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check).stdout


def write(root: Path, rel: str, data: str | bytes) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    (p.write_bytes if isinstance(data, bytes) else p.write_text)(data)


@pytest.fixture
def his(tmp_path):
    """His remote (a local bare repo) and his own computer's working copy (he commits there too)."""
    work = tmp_path / "javohir-pc"
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    git(work, "config", "user.name", "eraliyev-j")
    git(work, "config", "user.email", "j@example.com")
    for rel, data in {
        "README.md": "# the-suvyektiv-media",
        ".gitignore": "node_modules/\n",
        "posted.md": POSTED,
        "brand/voice.md": VOICE,
        "brand/voice-template.md": "# template — ignore",
        "guidance-book.md": "# Montaj uslubim\n- Subtitr: Inter Bold 64\n",
        ".claude/skills/doktor-h2o-workflow/SKILL.md": "---\nname: doktor-h2o-workflow\ndescription: Doktor H2O reel ish tartibi.\n---\n# Workflow\nBitta reel = bitta ilmiy da'vo.\n",
        ".claude/skills/ig-reel/SKILL.md": "---\nname: ig-reel\ndescription: Reel hooks and beats.\n---\nbody\n",
        "posts/2026-10-15-choynak/slides.json": "{}",
        "audits/2026-10-28.md": "# Audit 2026-10-28\nMedian views ~1600.\n",
        "reels/2026-11-05-layfhak/reel.mp4": b"\x00his video",
        "reels/2026-11-05-layfhak/cover.jpg": b"\xff\xd8his cover",
        "reels/2026-11-05-layfhak/script.md": SCRIPT_MD,
        "reels/2026-11-05-layfhak/src/hack.py": "print('render')\n",
        "reels/2026-11-10-ichak-tayoqchasi/reel.mp4": b"\x00ecoli",
        "reels/2026-11-10-ichak-tayoqchasi/cover.jpg": b"\xff\xd8ecoli",
    }.items():
        write(work, rel, data)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "Add 10.11 ichak tayoqchasi reel")
    remote = tmp_path / "the-suvyektiv-media.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(remote)], check=True)
    git(work, "remote", "add", "origin", str(remote))
    git(work, "fetch", "-q", "origin")
    git(work, "branch", "-q", "-u", "origin/main")
    return {"remote": remote, "work": work}


def existing(settings, remote: Path) -> ContentRepo:
    (settings.root / "config.local.toml").write_text(
        f'[github]\ncontent_mode = "existing"\ncontent_existing = "eraliyev-j/the-suvyektiv-media"\n'
        f'content_remote = "{remote}"\n', encoding="utf-8")
    return ContentRepo(settings)


def new_reel(tmp_path) -> tuple[Path, Path, Path]:
    v, c, s = tmp_path / "render.mp4", tmp_path / "owner_cover.jpg", tmp_path / "script.md"
    v.write_bytes(b"\x00new reel video")
    c.write_bytes(b"\xff\xd8owner cover")
    s.write_text("# Kran suvi\n", encoding="utf-8")
    return v, c, s


def remote_files(remote: Path, ref: str = "main") -> list[str]:
    return git(remote, "ls-tree", "-r", "--name-only", ref).split()


def changed(remote: Path, a: str, b: str = "main") -> list[str]:
    return git(remote, "diff", "--name-only", a, b).split()


def test_parse_repo_ref():
    for text in ("https://github.com/eraliyev-j/the-suvyektiv-media", "github.com/eraliyev-j/the-suvyektiv-media.git",
                 "git@github.com:eraliyev-j/the-suvyektiv-media.git", "eraliyev-j/the-suvyektiv-media",
                 "https://github.com/eraliyev-j/the-suvyektiv-media/tree/main/reels"):
        assert parse_repo_ref(text) == "eraliyev-j/the-suvyektiv-media"
    assert parse_repo_ref("https://gitlab.com/a/b") == "" and parse_repo_ref("salom") == ""


def test_choosing_an_existing_repo_is_saved_per_computer_and_clones_instead_of_init(settings, his):
    repo = ContentRepo(settings)
    repo.choose("existing", "https://github.com/eraliyev-j/the-suvyektiv-media")
    local = (settings.root / "config.local.toml").read_text()
    assert 'content_mode = "existing"' in local and 'content_existing = "eraliyev-j/the-suvyektiv-media"' in local
    assert "config.local.toml" not in git(settings.root, "ls-files")            # never in the code repo
    assert repo.remote_url() == "https://github.com/eraliyev-j/the-suvyektiv-media.git"
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    log = git(repo.path, "log", "--format=%s").splitlines()
    assert log == ["Add 10.11 ichak tayoqchasi reel"]                            # his history, no new "init" commit
    assert (repo.path / "brand" / "voice.md").exists() and (repo.path / "posted.md").exists()
    assert not (repo.path / "reels" / "2026-11-05-layfhak" / "reel.mp4").exists()   # sparse: videos stay remote
    assert "reels/2026-11-05-layfhak/reel.mp4" in repo.tree("reels")
    st = repo.status()
    assert st["mode"] == "existing" and st["count"] == 2 and st["branch"] == "main" and st["last_sync"]


def test_his_layout_is_detected_and_followed(settings, his, tmp_path):
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    assert repo.layout() == "named"
    v, c, s = new_reel(tmp_path)
    files = repo.reel_files("2026-11-12-kran-suvi", v, c, s, {"research.md": s})
    assert list(files) == ["reel.mp4", "cover.jpg", "script.md"]
    before = git(his["remote"], "rev-parse", "main").strip()
    res = repo.publish("2026-11-12-kran-suvi", files, "Kran suvi")
    assert res.pushed and res.folder == "reels/2026-11-12-kran-suvi" and "the-suvyektiv-media" in res.note
    # nothing outside the new reel folder changed
    assert changed(his["remote"], before) == ["reels/2026-11-12-kran-suvi/cover.jpg", "reels/2026-11-12-kran-suvi/reel.mp4",
                                              "reels/2026-11-12-kran-suvi/script.md"]
    assert git(his["remote"], "show", "main:reels/2026-11-12-kran-suvi/reel.mp4") == "\x00new reel video"
    assert git(his["remote"], "rev-list", "--count", "main").strip() == "2"


def test_a_repo_without_his_layout_keeps_our_default(settings, tmp_path):
    work = tmp_path / "plain"
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    write(work, "notes.md", "x")
    git(work, "add", "-A")
    git(work, "-c", "user.name=a", "-c", "user.email=a@b", "commit", "-q", "-m", "first")
    remote = tmp_path / "plain.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(remote)], check=True)
    repo = existing(settings, remote)
    repo.ensure_local()
    v, c, s = new_reel(tmp_path)
    assert repo.layout() == "default"
    assert list(repo.reel_files("2026-11-12-suv", v, c, s)) == ["2026-11-12-suv.mp4", "2026-11-12-suv_cover.jpg", "script.md"]


def test_publish_on_top_of_a_remote_that_moved_ahead_rebases_without_force(settings, his, tmp_path, monkeypatch):
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    # He commits from his own computer after our clone.
    write(his["work"], "reels/2026-11-11-qor-suvi/reel.mp4", b"\x00snow")
    git(his["work"], "add", "-A")
    git(his["work"], "commit", "-q", "-m", "Add 11.11 qor suvi reel")
    git(his["work"], "push", "-q", "origin", "main")
    his_head = git(his["remote"], "rev-parse", "main").strip()
    calls = []
    real = subprocess.run

    def spy(cmd, *a, **k):
        if isinstance(cmd, list) and cmd[:1] == ["git"]:
            calls.append(cmd)
        return real(cmd, *a, **k)
    monkeypatch.setattr(subprocess, "run", spy)
    v, c, s = new_reel(tmp_path)
    res = repo.publish("2026-11-12-kran-suvi", repo.reel_files("2026-11-12-kran-suvi", v, c, s), "Kran suvi")
    assert res.pushed
    history = git(his["remote"], "log", "--format=%s", "main").splitlines()
    assert history[:3] == ["Reel: Kran suvi (2026-11-12)", "Add 11.11 qor suvi reel", "Add 10.11 ichak tayoqchasi reel"]
    assert git(his["remote"], "merge-base", "--is-ancestor", his_head, "main", check=False) == ""   # his commit kept
    pushes = [cmd for cmd in calls if "push" in cmd]
    assert pushes and not any(x in ("--force", "-f", "--force-with-lease") or x.startswith("+")
                              for cmd in pushes for x in cmd[cmd.index("push"):])


def test_push_rejected_because_he_pushed_meanwhile_is_rebased_and_retried(settings, his, tmp_path, monkeypatch):
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    orig = repo.sync
    state = {"n": 0}

    def sync_then_he_pushes():
        out = orig()
        state["n"] += 1
        if state["n"] == 2:                        # after our pre-push sync, he pushes: our push is rejected once
            write(his["work"], "audits/2026-11-12.md", "# new audit")
            git(his["work"], "add", "-A")
            git(his["work"], "commit", "-q", "-m", "Audit 12.11")
            git(his["work"], "push", "-q", "origin", "main")
        return out
    monkeypatch.setattr(repo, "sync", sync_then_he_pushes)
    v, c, s = new_reel(tmp_path)
    res = repo.publish("2026-11-12-kran-suvi", repo.reel_files("2026-11-12-kran-suvi", v, c, s), "Kran suvi")
    assert res.pushed and state["n"] >= 3
    assert git(his["remote"], "log", "--format=%s", "-2", "main").splitlines() == ["Reel: Kran suvi (2026-11-12)", "Audit 12.11"]


def test_conflict_keeps_the_reel_locally_and_reports(settings, his, tmp_path):
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    v, c, s = new_reel(tmp_path)
    files = repo.reel_files("2026-11-12-kran-suvi", v, c, s)
    # Offline moment (his remote unreachable): we commit locally ...
    hidden = his["remote"].with_name("away.git")
    his["remote"].rename(hidden)
    res = repo.publish("2026-11-12-kran-suvi", files, "Kran suvi")
    assert res.committed and not res.pushed
    hidden.rename(his["remote"])
    # ... meanwhile he created a reel folder with the same name on his computer.
    write(his["work"], "reels/2026-11-12-kran-suvi/reel.mp4", b"\x00HIS OWN")
    git(his["work"], "add", "-A")
    git(his["work"], "commit", "-q", "-m", "Add 12.11 kran suvi")
    git(his["work"], "push", "-q", "origin", "main")
    his_head = git(his["remote"], "rev-parse", "main").strip()
    pushed, note = repo.push()
    assert not pushed and note == NOTE_CONFLICT and "fayllaringizga tegilmadi" in note
    assert git(his["remote"], "rev-parse", "main").strip() == his_head          # his remote untouched
    assert git(his["remote"], "show", "main:reels/2026-11-12-kran-suvi/reel.mp4") == "\x00HIS OWN"
    assert repo.pending() == ["2026-11-12-kran-suvi"]                           # our reel kept on a local branch
    kept = git(repo.path, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{PENDING_PREFIX}").split()
    assert kept and git(repo.path, "show", f"{kept[0]}:reels/2026-11-12-kran-suvi/reel.mp4") == "\x00new reel video"
    assert repo.status()["pending"] == 1


def test_never_overwrites_his_folder_of_the_same_name(settings, his, tmp_path):
    write(his["work"], "reels/2026-11-12-kran-suvi/reel.mp4", b"\x00HIS OWN")
    git(his["work"], "add", "-A")
    git(his["work"], "commit", "-q", "-m", "Add 12.11 kran suvi")
    git(his["work"], "push", "-q", "origin", "main")
    repo = existing(settings, his["remote"])
    v, c, s = new_reel(tmp_path)
    res = repo.publish("2026-11-12-kran-suvi", repo.reel_files("2026-11-12-kran-suvi", v, c, s), "Kran suvi")
    assert res.pushed and res.folder == "reels/2026-11-12-kran-suvi-2"
    assert git(his["remote"], "show", "main:reels/2026-11-12-kran-suvi/reel.mp4") == "\x00HIS OWN"


def test_posted_md_line_in_his_format(settings, his, tmp_path):
    repo = existing(settings, his["remote"])
    v, c, s = new_reel(tmp_path)
    repo.publish("2026-11-12-kran-suvi", repo.reel_files("2026-11-12-kran-suvi", v, c, s), "Kran suvi")
    before = git(his["remote"], "rev-parse", "main").strip()
    values = {"date": "2026-11-12", "title": "Kran suvi", "hook": "Kran suvini ichsa bo'ladimi?",
              "topic": "Kran suvi (Buffer navbatida: Instagram, YouTube, LinkedIn)"}
    assert repo.append_posted(values)
    text = git(his["remote"], "show", "main:posted.md")
    assert text.startswith(POSTED)                                              # his lines unchanged
    assert text.endswith("2026-11-12 | REEL | Kran suvi (Buffer navbatida: Instagram, YouTube, LinkedIn) | "
                         "Kran suvini ichsa bo'ladimi? | -\n")
    assert "posted" not in text[len(POSTED):].lower()                           # never claims "posted"
    assert changed(his["remote"], before) == ["posted.md"]
    assert repo.append_posted(values)                                           # a retried job adds nothing
    assert git(his["remote"], "show", "main:posted.md").count("Kran suvi (Buffer") == 1


def test_posted_md_edited_by_him_at_the_same_time_is_re_read(settings, his, tmp_path, monkeypatch):
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    orig = repo.sync
    state = {"n": 0}

    def he_appends_too():
        out = orig()
        state["n"] += 1
        if state["n"] == 1:
            p = his["work"] / "posted.md"
            p.write_text(p.read_text() + "2026-11-12 | 1 Karusel | Uning qatori | hook | 1\n")
            git(his["work"], "commit", "-qam", "posted")
            git(his["work"], "push", "-q", "origin", "main")
        return out
    monkeypatch.setattr(repo, "sync", he_appends_too)
    values = {"date": "2026-11-12", "title": "Kran suvi", "hook": "h", "topic": "Kran suvi (Buffer navbatida)"}
    assert repo.append_posted(values)
    text = git(his["remote"], "show", "main:posted.md")
    assert "Uning qatori" in text and text.endswith("| REEL | Kran suvi (Buffer navbatida) | h | -\n")


def test_guard_still_refuses_the_code_repo(settings, his):
    repo = ContentRepo(settings)
    with pytest.raises(ContentPushRefused):
        repo.choose("existing", "https://github.com/Abdurahman0/social-automation")
    git(settings.root, "remote", "add", "origin", str(his["remote"]))         # even when it is a remote of the code folder
    with pytest.raises(ContentPushRefused):
        existing(settings, his["remote"]).ensure_local()


def test_switching_repo_keeps_the_old_clone(settings, his, tmp_path):
    old = ContentRepo(settings)
    old.ensure_local()                                                          # today's own new repo
    (old.path / "reels").mkdir()
    (old.path / "reels" / "keep.txt").write_text("mine")
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    kept = [p for p in repo.path.parent.iterdir() if p.name.startswith("content-repo.")]
    assert len(kept) == 1 and (kept[0] / "reels" / "keep.txt").read_text() == "mine"
    (settings.root / "config.local.toml").write_text('[github]\ncontent_mode = "new"\n')
    ContentRepo(settings).ensure_local()                                       # back to a new repo: his clone kept too
    assert len([p for p in repo.path.parent.iterdir() if p.name.startswith("content-repo.")]) == 2


def test_brand_rules_and_examples_are_read(settings, his):
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    b = repo.brand()
    assert b["max_seconds"] == 45 and b["min_seconds"] == 30
    assert "suvyektiv fikrlaymiz" in b["text"] and "Bitta reel = bitta ilmiy da'vo" in b["text"]
    assert "template" not in b["text"] and "ig-reel" not in " ".join(b["files"])
    ex = repo.examples()
    assert "5 ta suv tejash layfhagi" in ex and "Median views" in ex
    assert ContentRepo(settings).brand() is not None
    (settings.root / "config.local.toml").write_text('[github]\ncontent_mode = "new"\n')
    assert ContentRepo(settings).brand() is None                               # our own new repo: no brand files


def test_the_skills_page_lists_the_content_repos_skills(settings, his):
    from socialauto.web.skills import scan
    repo = existing(settings, his["remote"])
    repo.ensure_local()
    data = scan(settings.root / "no-claude", settings.root, set(), content_dir=repo.skills_dir())
    mine = [s for s in data["skills"] if s["source"] == "Kontent reposi"]
    assert {s["slug"] for s in mine} == {"doktor-h2o-workflow", "ig-reel"}
    assert any(g["label"] == "Kontent reposi" for g in data["groups"])


@pytest.mark.skipif(not os.environ.get("SA_SUV_BARE"), reason="set SA_SUV_BARE to a local bare copy of his real repo")
def test_on_a_local_copy_of_his_real_repo(settings, tmp_path):
    src = Path(os.environ["SA_SUV_BARE"])
    remote = tmp_path / "copy.git"
    subprocess.run(["git", "clone", "-q", "--bare", "--no-local", str(src), str(remote)], check=True)
    repo = existing(settings, remote)
    repo.ensure_local()
    assert repo.layout() == "named" and repo.brand()["max_seconds"] == 45
    v, c, s = new_reel(tmp_path)
    before = git(remote, "rev-parse", "main").strip()
    res = repo.publish("2026-11-12-kran-suvi", repo.reel_files("2026-11-12-kran-suvi", v, c, s), "Kran suvi")
    assert res.pushed
    assert repo.append_posted({"date": "2026-11-12", "title": "Kran suvi", "hook": "h", "topic": "Kran suvi (Buffer navbatida)"})
    assert sorted(changed(remote, before)) == ["posted.md", "reels/2026-11-12-kran-suvi/cover.jpg",
                                               "reels/2026-11-12-kran-suvi/reel.mp4", "reels/2026-11-12-kran-suvi/script.md"]


# --- the whole owner flow into HIS repo ---------------------------------------------------------------------------
def test_full_flow_into_his_repo_follows_his_rules(settings, his, tmp_path, clock, monkeypatch):
    """Research -> script -> voice -> video -> cover -> his repo + Buffer queue + posted.md, all on a local copy."""
    import asyncio
    import shutil

    from conftest import (SAMPLE_VOICE, FakeClaude, FakeProvider, FakeReelRenderer, FakeTranscriber, FileSession,
                          run_all_jobs, uz_script)
    from PIL import Image

    import socialauto.reel.broll as bm
    from socialauto.app import build_app, reel_places
    from socialauto.platforms.dryrun import DryRunLog
    from socialauto.reel import script as rs
    from socialauto.reel.buffer import DryRunBuffer
    from socialauto.store import BUFFER_PENDING
    from socialauto.telegram_bot import TelegramBot, buffer_message

    monkeypatch.setattr(bm.requests, "Session", FileSession)
    s = replace(settings, dry_run=False)                       # Buffer "really" queued (a stand-in, no network)
    existing(s, his["remote"])
    systems: dict[str, str] = {}

    class Recording(FakeClaude):
        def generate_json(self, task, prompt, schema, system_prompt, tools=(), timeout=None):
            systems[task] = system_prompt
            return super().generate_json(task, prompt, schema, system_prompt, tools, timeout)
    claude = Recording()
    claude.scripts = [uz_script(pad_words=10)]                 # ~40 s: inside his 30-45 s window
    app = build_app(s, claude=claude, transcriber=FakeTranscriber(rs.full_text(uz_script(pad_words=10))), clock=clock,
                    broll_providers=[FakeProvider(tmp_path)], reel_renderer=FakeReelRenderer(reel_places(s)),
                    buffer=DryRunBuffer(DryRunLog(s.dryrun_posts_path), clock))
    voice = tmp_path / "voice34.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "2", "-i", str(SAMPLE_VOICE), "-c", "copy",
                    str(voice)], check=True)
    wf = app.workflow
    before = git(his["remote"], "rev-parse", "main").strip()
    vid = wf.request_new()
    run_all_jobs(app)
    assert rs.window() == (30, 45)                             # his "maksimum 45 s"
    research_prompt = next(p for t, p in claude.calls if t.startswith("research"))
    assert "HIS PAST REELS" in research_prompt and "5 ta suv tejash layfhagi" in research_prompt
    wf.topic_decision(app.store.pending_approval(vid, "topic")["id"], 0)
    run_all_jobs(app)
    wf.script_decision(app.store.pending_approval(vid, "script")["id"], "approve")
    wf.route_voice(wf.save_raw_voice(voice, "voice", ".wav"))
    run_all_jobs(app)
    wf.video_decision(app.store.pending_approval(vid, "video")["id"], "approve")
    cover = tmp_path / "cover.jpg"
    Image.new("RGB", (1080, 1920), (20, 60, 120)).save(cover, "JPEG")
    bot = TelegramBot(app)

    async def dl(dest):
        shutil.copyfile(cover, dest)
    asyncio.run(bot.handle_cover(dl))
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == BUFFER_PENDING
    reel = wf.reels.get(vid)
    folder = f"reels/{reel['base']}"
    # only the new reel folder and one posted.md line changed in his repo
    assert sorted(changed(his["remote"], before)) == ["posted.md", f"{folder}/cover.jpg", f"{folder}/reel.mp4",
                                                      f"{folder}/script.md"]
    assert subprocess.run(["git", "-C", str(his["remote"]), "cat-file", "-s", f"main:{folder}/cover.jpg"],
                          capture_output=True, text=True).stdout.strip() == str(cover.stat().st_size)   # cover as is
    md = git(his["remote"], "show", f"main:{folder}/script.md")
    assert "## Ovoz matni (subtitr bilan bir xil)" in md and "1. (" in md and " s) " in md
    assert "## Raqamlar va manbalar" in md and "https://water.gov.uz/" in md and "## Caption" in md and "IG #suv" in md
    posted = git(his["remote"], "show", "main:posted.md").splitlines()[-1]
    assert posted.startswith(f"{clock().strftime('%Y-%m-%d')} | REEL | ") and "Buffer navbatida: Instagram, YouTube, LinkedIn" in posted
    assert posted.endswith(" | -")
    # his brand rules reached Claude for the script and the captions
    assert "suvyektiv fikrlaymiz" in systems["propose-reel-script"] and "Bitta reel = bitta ilmiy" in systems["research-topics"]
    assert "suvyektiv fikrlaymiz" in next(p for t, p in claude.calls if t == "write-captions")
    msg = buffer_message(app.store.video(vid)["title"], reel, False)
    assert "Reel sizning the-suvyektiv-media repongizga yuklandi" in msg
    assert f"https://github.com/eraliyev-j/the-suvyektiv-media/tree/main/{folder}" in msg
    rs.set_window_provider(None)
