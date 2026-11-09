"""The live analytics dashboard (FastAPI + a hand-built static frontend, no build step: light on memory).

Protected by the password in .env (DASHBOARD_PASSWORD). Sessions are HMAC-signed cookies (HttpOnly, SameSite=Strict)
with a server secret in data/web_secret (chmod 600). Failed logins are slowed down. The API returns only what the UI
shows: titles, numbers, times and opaque keys - never tokens, file paths or platform ids (law 6).
"""

from __future__ import annotations

import hashlib
import os
import hmac
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..analytics.collector import TASHKENT, UPDATED_KEY, Collector, make_collector, media_key
from ..analytics.metrics import Metrics
from ..config import Settings
from ..db import KV, Database, parse_iso
from ..store import STATUS_UZ, Store
from .. import slots

STATIC = Path(__file__).resolve().parent / "static"
COOKIE = "sa_session"
SESSION_DAYS = 30
REFRESH_MIN_INTERVAL = timedelta(minutes=5)


def clean_title(title: str) -> str:
    """A stock file name as a readable title: no extension, no hash-like codes, no doubled separators."""
    import re
    t = re.sub(r"\.(jpe?g|png|webm|mp4|ogv|tiff?|gif)$", "", title or "", flags=re.I)
    t = re.sub(r"\b[0-9a-f]{8,}\b", "", t, flags=re.I)
    t = re.sub(r"\s*[-–_]\s*(?=[-–_]|$)", "", t)
    t = re.sub(r"[_]+", " ", t)
    return " ".join(t.split()).strip(" -–") or "Manba"


def _secret(settings: Settings) -> bytes:
    path = settings.data_dir / "web_secret"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip().encode()


def make_token(secret: bytes, password: str, now: float | None = None) -> str:
    expires = int((now or time.time()) + SESSION_DAYS * 86400)
    pw = hashlib.sha256(password.encode()).hexdigest()[:16]      # changing the password logs everyone out
    sig = hmac.new(secret, f"{expires}.{pw}".encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def check_token(secret: bytes, password: str, token: str | None, now: float | None = None) -> bool:
    if not token or "." not in token or not password:
        return False
    expires, sig = token.split(".", 1)
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return False
    pw = hashlib.sha256(password.encode()).hexdigest()[:16]
    good = hmac.new(secret, f"{expires}.{pw}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, sig)


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
SETUP_OPEN = ("/setup", "/static/", "/api/setup", "/api/session", "/api/net", "/favicon")


def create_app(settings: Settings, db: Database | None = None, collector: Collector | None = None,
               clock=None, claude_dir: Path | None = None, repo_dir: Path | None = None, checks=None,
               github=None, claude_login=None, accounts=None, updater=None, content=None, restart=None) -> FastAPI:
    db = db or Database(settings.db_path)
    db.migrate()
    kv, store = KV(db), Store(db)
    clock = clock or (lambda: datetime.now(TASHKENT))
    collector = collector or make_collector(settings, db, kv, clock)
    secret = _secret(settings)
    fails: dict[str, list[float]] = {}
    refresh_lock = threading.Lock()
    app = FastAPI(title="Social Automation", docs_url=None, redoc_url=None, openapi_url=None)

    def today() -> date:
        return clock().astimezone(TASHKENT).date()

    env_path = settings.root / ".env"
    from .setup import SetupChecks
    checks = checks or SetupChecks(settings)
    from ..claude_login import ClaudeLogin
    from ..content_repo import ContentRepo
    from ..github_account import GitHubAccount
    from ..updater import Updater
    from .accounts import Accounts
    github = github or GitHubAccount(settings)
    claude_login = claude_login or ClaudeLogin(settings)
    accounts = accounts or Accounts(settings)
    updater = updater or Updater(repo_dir or settings.root)
    content = content or ContentRepo(settings, github)

    def password() -> str:
        """The dashboard password, read fresh from .env (the Setup page may have just set it)."""
        from .. import env_store
        # .env is the source of truth (read fresh); a real environment variable is the only other place.
        # The value loaded at startup is NOT used: it would outlive a cleared or reset .env.
        import os
        if env_path.exists() or not settings.dashboard_password:
            return env_store.read(env_path).get("DASHBOARD_PASSWORD") or os.environ.get("DASHBOARD_PASSWORD", "")
        return settings.dashboard_password            # tests / setups without a .env file

    def is_local(request: Request) -> bool:
        """This computer itself, not a request relayed by a proxy or tunnel (those come from 127.0.0.1 too)."""
        relayed = any(h in request.headers for h in ("x-forwarded-for", "forwarded", "cf-connecting-ip", "x-real-ip"))
        return bool(request.client) and request.client.host in LOCAL_HOSTS and not relayed

    def authed(request: Request) -> None:
        if not password():
            raise HTTPException(status_code=401, detail="setup")
        if not check_token(secret, password(), request.cookies.get(COOKIE)):
            raise HTTPException(status_code=401, detail="login")

    @app.middleware("http")
    async def headers(request: Request, call_next):
        path = request.url.path
        if not password() and not path.startswith(SETUP_OPEN):     # first start: everything leads to the Setup page
            if path.startswith("/api/"):
                return JSONResponse({"ok": False, "reason": "setup"}, status_code=401)
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/setup", status_code=307)
        if not password() and path.startswith(("/setup", "/api/setup")) and not is_local(request):
            return JSONResponse({"ok": False, "reason": "local_only"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse({"ok": False, "reason": exc.detail if isinstance(exc.detail, str) else "error"},
                            status_code=exc.status_code)

    # --- session ------------------------------------------------------------------------------------------
    @app.get("/api/session")
    def session(request: Request) -> dict:
        return {"authenticated": bool(password()) and check_token(secret, password(), request.cookies.get(COOKIE)),
                "configured": bool(password())}

    password_value = password                                      # the login handler has a local named `password`

    @app.post("/api/login")
    def login(request: Request, response: Response, body: dict = Body(...)) -> dict:
        ip = request.client.host if request.client else "?"
        recent = [t for t in fails.get(ip, []) if t > time.time() - 600]
        if len(recent) >= 8:
            raise HTTPException(status_code=429, detail="too_many")
        password = str(body.get("password", ""))
        if not password_value() or not hmac.compare_digest(password.encode(), password_value().encode()):
            fails[ip] = recent + [time.time()]
            time.sleep(min(2.0, 0.25 * len(fails[ip])))
            raise HTTPException(status_code=401, detail="wrong_password")
        fails.pop(ip, None)
        response.set_cookie(COOKIE, make_token(secret, password_value()), max_age=SESSION_DAYS * 86400,
                            httponly=True, samesite="strict", secure=settings.web.public_url.startswith("https"))
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response) -> dict:
        response.delete_cookie(COOKIE)
        return {"ok": True}

    # --- data ---------------------------------------------------------------------------------------------
    def status_block() -> dict:
        now = clock()
        out = {}
        for p, connected in collector.connected().items():
            upd = kv.get(UPDATED_KEY.format(p))
            out[p] = {"connected": connected, "source": collector.source(p),
                      "updated_minutes": int((now - parse_iso(upd)).total_seconds() // 60) if upd else None,
                      "problem": {"auth": "auth"}.get(kv.get(f"analytics:{p}:error") or "", None)
                      if kv.get(f"analytics:{p}:error") else None}
        return {"platforms": out, "dry_run": settings.dry_run, "refresh_minutes": settings.analytics.refresh_minutes}

    @app.get("/api/status")
    def status(request: Request) -> dict:
        authed(request)
        return status_block()

    @app.get("/api/overview")
    def overview(request: Request, days: int = 30) -> dict:
        authed(request)
        days = max(1, min(365, days))
        return {**Metrics(db, today()).overview(days), "status": status_block()}

    @app.get("/api/series")
    def series(request: Request, metric: str = "views", start: str | None = None, end: str | None = None) -> dict:
        authed(request)
        if metric not in ("views", "followers", "engagement", "reach"):
            raise HTTPException(status_code=400, detail="metric")
        try:
            e = date.fromisoformat(end) if end else today()
            s = date.fromisoformat(start) if start else e - timedelta(days=29)
        except ValueError:
            raise HTTPException(status_code=400, detail="date") from None
        if s > e or (e - s).days > 400:
            raise HTTPException(status_code=400, detail="range")
        return Metrics(db, today()).series(metric, s, e)

    def public_video(row: dict) -> dict:
        row = {k: v for k, v in row.items() if k != "video_id"}
        row["thumb"] = f"/media/thumb/{row['thumb']}" if row.get("thumb") else None
        return row

    @app.get("/api/videos")
    def videos(request: Request) -> dict:
        authed(request)
        return {"videos": [public_video(r) for r in Metrics(db, today()).videos()]}

    @app.get("/api/videos/{key}")
    def video(request: Request, key: str) -> dict:
        authed(request)
        row = Metrics(db, today()).video(key)
        if not row:
            raise HTTPException(status_code=404, detail="not_found")
        return public_video(row)

    @app.get("/api/insights")
    def insights(request: Request, days: int = 30) -> dict:
        authed(request)
        m = Metrics(db, today())
        return {"best_times": m.best_times(), "top": [public_video(r) for r in m.top_videos(5)],
                "comparison": m.comparison(max(1, min(365, days)))}

    def reel_key(video_id: int) -> str:
        return media_key("reel", str(video_id))

    def reel_video(key: str) -> dict | None:
        for v in store.videos(limit=500):
            if reel_key(v["id"]) == key:
                return v
        return None

    @app.get("/api/pipeline")
    def pipeline(request: Request) -> dict:
        authed(request)
        return reel_pipeline()

    def reel_pipeline() -> dict:
        from ..reel.state import STAGES, STATUS_STAGE, Reels
        reels = Reels(db)
        rows = store.videos(limit=300)
        cols = []
        for key, label in STAGES:
            items = []
            for v in rows:
                stage = STATUS_STAGE.get(v["status"])
                if not stage or stage[0] != key:
                    continue
                if v["status"] == "done" and len([i for i in items if i["done"]]) >= 8:
                    continue
                r = reels.get(v["id"]) or {}
                items.append({"key": reel_key(v["id"]), "title": v["title"] or "Yangi tadqiqot",
                              "status": STATUS_UZ.get(v["status"], ""), "who": stage[1], "done": v["status"] == "done",
                              "version": r.get("version") or 0,
                              "date": r.get("base", "")[:10] or None,
                              "slot": slots.describe(settings.schedule, parse_iso(v["slot_at"])) if v["slot_at"] else None,
                              "origin_voice": v["origin"] == "voice"})
            cols.append({"key": key, "label": label, "items": items})
        return {"columns": cols, "dry_run": settings.dry_run}

    # --- approved reels (the owner pressed Approve on the video; from there they go into Buffer's queue) --------
    APPROVED = ("cover_waiting", "publishing", "buffer_pending", "story_pending", "done")
    PLATFORM_NAMES = {"instagram": "Instagram", "youtube": "YouTube", "linkedin": "LinkedIn"}
    BUFFER_UZ = {"scheduled": "Navbatda", "sending": "Joylanmoqda", "sent": "Chiqdi", "draft": "Buffer'da qoralama",
                 "needs_approval": "Buffer'da tasdiq kutilmoqda", "error": "Buffer xatosi",
                 "missing": "Buffer'dan o'chirilgan"}

    def when_text(value: str | None) -> str | None:
        return slots.describe(settings.schedule, parse_iso(value)) if value else None

    def buffer_rows(v: dict, r: dict) -> list[dict]:
        """One row per platform the reel went to: its Buffer state in words, the time, the live link."""
        states, live = r.get("buffer") or {}, r.get("live_links") or {}
        rows = []
        for svc in (r.get("drafts") or {}):
            st = states.get(svc) or {}
            status = st.get("status") or ("sent" if live.get(svc) else "scheduled")
            if str((r.get("drafts") or {}).get(svc, "")).startswith("dryrun-"):     # made while dry_run was on
                label = "Sinov rejimi — Buffer'ga yuborilmagan"
            else:
                label = BUFFER_UZ.get(status, "Buffer'da")
            rows.append({"platform": svc, "name": PLATFORM_NAMES.get(svc, svc.title()), "status": status, "label": label,
                         "when": when_text(st.get("sent_at") if status == "sent" else st.get("due_at")),
                         "link": live.get(svc) or (st.get("link") if status == "sent" else None)})
        return rows

    def reel_media(v: dict, r: dict) -> dict:
        render = store.render(v["render_id"]) if v.get("render_id") else None
        video_ok = bool(render and render.get("video_path") and Path(render["video_path"]).exists())
        cover_ok = bool(r.get("cover_path") and Path(r["cover_path"]).exists())
        key = reel_key(v["id"])
        return {"video_url": f"/media/reelvideo/{key}" if video_ok else None,
                "cover_url": f"/media/reelcover/{key}" if cover_ok else None}

    @app.get("/api/approved")
    def approved(request: Request) -> dict:
        authed(request)
        from ..reel.state import Reels
        reels = Reels(db)
        items = []
        for v in store.videos(APPROVED, limit=300):
            r = reels.get(v["id"]) or {}
            items.append({"key": reel_key(v["id"]), "title": v["title"] or "Reel", "status": STATUS_UZ.get(v["status"], ""),
                          "date": r.get("base", "")[:10] or None,
                          "platforms": buffer_rows(v, r), **reel_media(v, r)})
        return {"items": items, "dry_run": settings.dry_run}

    def reel_file(key: str, which: str) -> Path:
        from ..reel.state import Reels
        v = reel_video(key)
        if not v or v["status"] not in APPROVED:
            raise HTTPException(status_code=404, detail="not_found")
        r = Reels(db).get(v["id"]) or {}
        if which == "cover":
            path = r.get("cover_path")
        else:
            render = store.render(v["render_id"]) if v.get("render_id") else None
            path = render.get("video_path") if render else None
        if not path or not Path(path).exists():
            raise HTTPException(status_code=404, detail="not_found")
        return Path(path)

    @app.get("/media/reelvideo/{key}")
    def reel_video_file(request: Request, key: str):
        authed(request)
        return FileResponse(reel_file(key, "video"), media_type="video/mp4", headers={"Cache-Control": "private, max-age=600"})

    @app.get("/media/reelcover/{key}")
    def reel_cover_file(request: Request, key: str):
        authed(request)
        path = reel_file(key, "cover")
        media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(path, media_type=media, headers={"Cache-Control": "private, max-age=600"})

    @app.get("/api/reels/{key}")
    def reel_detail(request: Request, key: str) -> dict:
        authed(request)
        from ..app import reel_places
        from ..reel import broll as broll_mod, research as research_mod, script as script_mod
        from ..reel.state import STAGES, STATUS_STAGE, Reels
        v = reel_video(key)
        if not v:
            raise HTTPException(status_code=404, detail="not_found")
        r = Reels(db).get(v["id"]) or {}
        places = reel_places(settings)
        base = r.get("base", "")
        work = places.work(base) if base else None
        research = None
        if r.get("research_file") and Path(r["research_file"]).exists():
            research = research_mod.parse_markdown(Path(r["research_file"]).read_text(encoding="utf-8"))
            for tp in research["topics"]:
                for f in tp["facts"]:
                    f["url"] = f["url"] if f["url"].startswith("http") else None
        script = store.script(v["id"]) or {}
        parts = [{"label": script_mod.PART_UZ.get(p["part"], p["part"]), "text": p["text"], "info": p.get("info")}
                 for p in script.get("parts", [])] if "parts" in script else []
        sources = [{"part": script_mod.PART_UZ.get(c.part, c.part), "kind": "video" if c.kind == "video" else "rasm",
                    "provider": c.provider, "author": c.author, "license": c.license,
                    "link": c.source_url if c.source_url.startswith("http") else None, "title": clean_title(c.title)}
                   for c in (broll_mod.load_sources(work) if work else [])]
        versions = []
        for path in places.versions(base) if base else []:
            n = int(path.stem.rsplit("_v", 1)[1])
            versions.append({"n": n, "size_mb": round(path.stat().st_size / 1e6, 1)})
        frames = []
        n = r.get("version") or 0
        if work and n and (work / f"frames_v{n}").is_dir():
            for i, f in enumerate(sorted((work / f"frames_v{n}").glob("*.jpg"))):
                frames.append({"label": script_mod.PART_UZ.get(f.stem.split("-", 1)[1], f.stem), "src": f"/media/reelframe/{key}/{n}/{i}"})
        stage = STATUS_STAGE.get(v["status"], ("", ""))
        names = {"instagram": "Instagram", "youtube": "YouTube", "linkedin": "LinkedIn"}
        return {
            "title": v["title"] or "Yangi tadqiqot", "status": STATUS_UZ.get(v["status"], ""), "who": stage[1],
            "stage": dict(STAGES).get(stage[0], ""), "stage_key": stage[0], "name": base,
            "slot": slots.describe(settings.schedule, parse_iso(v["slot_at"])) if v["slot_at"] else None,
            "version": n, "versions": versions, "research": research, "topic_index": r.get("topic_index"),
            "script": {"title": script.get("title"), "key_fact": script.get("key_fact"), "parts": parts},
            "sources": sources, "checklist": r.get("checklist") or {}, "frames": frames,
            "drafts": [names.get(k, k) for k in (r.get("drafts") or {})], "git": r.get("git_note"),
            "live": r.get("live_link"), "story": bool(r.get("story_draft")), "fixes": r.get("fix_notes") or [],
            "cover": bool(r.get("cover_path")),
            "approved": v["status"] in APPROVED, "buffer": buffer_rows(v, r) if v["status"] in APPROVED else [],
            "captions": {k: (r.get("captions") or {}).get(k) for k in
                         ("instagram", "youtube_title", "youtube_description", "linkedin", "story_text")}
            if r.get("captions") else None,
            **(reel_media(v, r) if v["status"] in APPROVED else {"video_url": None, "cover_url": None}),
            "dry_run": settings.dry_run,
        }

    @app.get("/media/reelframe/{key}/{version}/{index}")
    def reel_frame(request: Request, key: str, version: int, index: int):
        authed(request)
        from ..app import reel_places
        from ..reel.state import Reels
        v = reel_video(key)
        r = Reels(db).get(v["id"]) if v else None
        if not r:
            raise HTTPException(status_code=404, detail="not_found")
        folder = reel_places(settings).work(r["base"]) / f"frames_v{int(version)}"
        files = sorted(folder.glob("*.jpg")) if folder.is_dir() else []
        if not 0 <= index < len(files):
            raise HTTPException(status_code=404, detail="not_found")
        return FileResponse(files[index], media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})

    @app.post("/api/refresh")
    def refresh(request: Request) -> dict:
        authed(request)
        last = kv.get("analytics:manual_refresh")
        now = clock()
        if last and now - parse_iso(last) < REFRESH_MIN_INTERVAL:
            return {"ok": True, "skipped": True}
        if not refresh_lock.acquire(blocking=False):
            return {"ok": True, "skipped": True}
        try:
            kv.set("analytics:manual_refresh", now.isoformat())
            collector.refresh()
        finally:
            refresh_lock.release()
        return {"ok": True, "skipped": False}

    # --- skills and repo (read-only views of this computer) -----------------------------------------------
    @app.get("/api/skills")
    def skills(request: Request) -> dict:
        authed(request)
        from .skills import cached_scan
        return cached_scan(claude_dir or settings.claude.config_dir, repo_dir or settings.root)

    @app.get("/api/repo")
    def repo(request: Request) -> dict:
        """Task 07: the user's OWN content repo (where his reels go) and the read-only code repo (updates only)."""
        authed(request)
        from .repo import never_pushed, status as repo_status
        code_root = repo_dir or settings.root
        st = content.status()
        history = repo_status(content.path).get("history", []) if st["exists"] else []
        code = repo_status(code_root)
        return {"account": github.public(), "content": st, "history": history,
                "code": {"repo": settings.github.code_repo, "is_repo": code.get("is_repo", False),
                         "branch": code.get("branch", "main"), "url": f"https://github.com/{settings.github.code_repo}"},
                "never": never_pushed(code_root)}

    # --- media --------------------------------------------------------------------------------------------
    @app.get("/media/thumb/{key}")
    def thumb(request: Request, key: str):
        authed(request)
        path = Metrics(db).thumb_path(key)
        if not path or not Path(path).exists():
            raise HTTPException(status_code=404, detail="not_found")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    # --- Task 07: the user's own accounts, internet state, updates -----------------------------------------
    from ..netcheck import online

    @app.get("/api/net")
    def net() -> dict:
        return {"online": online()}

    def guard(request: Request) -> None:
        setup_guard(request)
        if not password():
            raise HTTPException(status_code=400, detail="password_first")

    def gh_call(fn, *a):
        from ..github_account import GitHubError
        try:
            return fn(*a)
        except GitHubError as exc:
            raise HTTPException(status_code=400, detail=exc.reason) from None

    def acc_call(fn, *a):
        from .accounts import AccountError
        try:
            return fn(*a)
        except AccountError as exc:
            raise HTTPException(status_code=400, detail=exc.reason) from None

    @app.get("/api/accounts")
    def accounts_view(request: Request) -> dict:
        guard(request)
        return {"github": github.public(), "claude": {**claude_login.status(), **claude_login.view()},
                "instagram": accounts.instagram_view(), "youtube": accounts.youtube_view(),
                "content": content.status()}

    @app.post("/api/accounts/github/device")
    def gh_device(request: Request) -> dict:
        guard(request)
        return gh_call(github.start_device)

    @app.post("/api/accounts/github/poll")
    def gh_poll(request: Request) -> dict:
        guard(request)
        res = github.poll_device()
        return {**res, "account": github.public() if res["state"] == "done" else None}

    @app.post("/api/accounts/github/token")
    def gh_token(request: Request, body: dict = Body(...)) -> dict:
        guard(request)
        info = gh_call(github.use_token, str(body.get("token", "")))
        return {"ok": True, "repo_missing": bool(info.get("repo_missing")), "account": github.public()}

    @app.post("/api/accounts/github/disconnect")
    def gh_disconnect(request: Request) -> dict:
        guard(request)
        github.disconnect()
        return {"ok": True}

    @app.post("/api/accounts/claude/start")
    def claude_start(request: Request) -> dict:
        guard(request)
        return claude_login.start()

    @app.post("/api/accounts/claude/code")
    def claude_code(request: Request, body: dict = Body(...)) -> dict:
        guard(request)
        return {**claude_login.submit_code(str(body.get("code", ""))), **claude_login.status()}

    @app.post("/api/accounts/instagram/start")
    def ig_start(request: Request) -> dict:
        guard(request)
        return {"url": acc_call(accounts.instagram_start)}

    @app.get("/api/accounts/instagram/callback")
    def ig_callback(request: Request):
        """Opened by Meta's redirect: authorised by the single-use state, not by the (SameSite=Strict) cookie."""
        from fastapi.responses import RedirectResponse
        q = request.query_params
        if q.get("error") or not q.get("code"):
            accounts.take_state(q.get("state", ""), "instagram")
            return RedirectResponse("/#/settings/stats?r=ig_cancel", status_code=303)
        try:
            accounts.instagram_callback(q["code"], q.get("state", ""))
        except Exception as exc:                          # noqa: BLE001
            return RedirectResponse(f"/#/settings/stats?r=ig_{getattr(exc, 'reason', 'rejected')}", status_code=303)
        return RedirectResponse("/#/settings/stats?r=ig_ok", status_code=303)

    @app.post("/api/accounts/instagram/token")
    def ig_token(request: Request, body: dict = Body(...)) -> dict:
        guard(request)
        return {"ok": True, **acc_call(accounts.instagram_token, str(body.get("token", "")))}

    @app.post("/api/accounts/instagram/disconnect")
    def ig_disconnect(request: Request) -> dict:
        guard(request)
        accounts.instagram_disconnect()
        return {"ok": True}

    @app.post("/api/accounts/youtube/client")
    def yt_client(request: Request, body: dict = Body(...)) -> dict:
        guard(request)
        text = str(body.get("text", ""))
        if len(text) > 20000:
            raise HTTPException(status_code=400, detail="bad_client")
        return acc_call(accounts.youtube_client, text)

    @app.post("/api/accounts/youtube/start")
    def yt_start(request: Request) -> dict:
        guard(request)
        return {"url": acc_call(accounts.youtube_start)}

    @app.post("/api/accounts/youtube/disconnect")
    def yt_disconnect(request: Request) -> dict:
        guard(request)
        accounts.youtube_disconnect()
        return {"ok": True}

    @app.get("/api/update")
    def update_status(request: Request, force: int = 0) -> dict:
        guard(request)
        return updater.status(fetch=True, force=bool(force))

    @app.post("/api/update")
    def update_apply(request: Request) -> dict:
        guard(request)
        res = updater.apply()
        if res.get("ok") and restart is not None:
            threading.Timer(2.0, restart).start()           # reply first, then the service manager restarts us
        return res

    # --- frontend -----------------------------------------------------------------------------------------
    # --- Setup ("Sozlash") and Settings ("Sozlamalar") ---------------------------------------------------------
    from .. import env_store

    def setup_guard(request: Request) -> None:
        """Before a password exists: only from this computer (the middleware checks). After: the password."""
        if password():
            authed(request)

    def save(updates: dict[str, str]) -> None:
        env_store.write(env_path, updates, settings.root / ".env.example")

    @app.get("/api/setup/state")
    def setup_state(request: Request) -> dict:
        setup_guard(request)
        values = env_store.read(env_path)
        if not values.get("DASHBOARD_PASSWORD") and password():
            values["DASHBOARD_PASSWORD"] = password()
        return {"configured": bool(password()), "values": env_store.public_view(values),
                "dry_run": settings.dry_run, "model": checks.model(), "claude": checks.claude()}

    @app.post("/api/setup/password")
    def setup_password(request: Request, response: Response, body: dict = Body(...)) -> dict:
        setup_guard(request)
        new = env_store.clean_value(str(body.get("password", "")))
        if len(new) < 8:
            raise HTTPException(status_code=400, detail="too_short")
        save({"DASHBOARD_PASSWORD": new})
        response.set_cookie(COOKIE, make_token(secret, new), max_age=SESSION_DAYS * 86400, httponly=True,
                            samesite="strict", secure=settings.web.public_url.startswith("https"))
        return {"ok": True}

    @app.post("/api/setup/save")
    def setup_save(request: Request, body: dict = Body(...)) -> dict:
        setup_guard(request)
        if not password():
            raise HTTPException(status_code=400, detail="password_first")
        updates = {}
        for key, value in (body.get("values") or {}).items():
            if key not in env_store.KEYS or key == "DASHBOARD_PASSWORD" or value is None:
                continue
            value = env_store.clean_value(str(value))
            problem = checks.validate(key, value)
            if problem:
                raise HTTPException(status_code=400, detail=problem)
            updates[key] = value
        if updates:
            save(updates)
        return {"ok": True, "saved": sorted(updates)}

    @app.post("/api/setup/check/{what}")
    def setup_check(request: Request, what: str, body: dict = Body(default={})) -> dict:
        setup_guard(request)
        values = env_store.read(env_path)
        if what == "telegram":
            return checks.telegram(env_store.clean_value(str(body.get("value") or values.get("TELEGRAM_BOT_TOKEN", ""))))
        if what == "buffer":
            return checks.buffer(env_store.clean_value(str(body.get("value") or values.get("BUFFER_API_KEY", ""))))
        if what == "claude":
            return checks.claude()
        if what == "model":
            return checks.model()
        raise HTTPException(status_code=404, detail="not_found")

    @app.get("/setup", response_class=HTMLResponse)
    def setup_page() -> HTMLResponse:
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        q = request.query_params
        if q.get("state") and accounts.owns_state(q["state"], "youtube"):   # Google's redirect back (Desktop client)
            from fastapi.responses import RedirectResponse
            if q.get("error") or not q.get("code"):
                accounts.take_state(q["state"], "youtube")
                return RedirectResponse("/#/settings/stats?r=yt_cancel", status_code=303)
            try:
                accounts.youtube_callback(q["code"], q["state"])
            except Exception as exc:                      # noqa: BLE001
                return RedirectResponse(f"/#/settings/stats?r=yt_{getattr(exc, 'reason', 'rejected')}", status_code=303)
            return RedirectResponse("/#/settings/stats?r=yt_ok", status_code=303)
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.state.collector = collector
    return app


def serve(settings: Settings) -> None:
    import uvicorn
    from ..runner import RESTART_CODE
    uvicorn.run(create_app(settings, restart=lambda: os._exit(RESTART_CODE)), host=settings.web.host, port=settings.web.port, log_level="warning",
                proxy_headers=False)


__all__ = ["create_app", "serve", "make_token", "check_token", "Any"]
