"""Command line: `python -m socialauto <command>`.

    run                 the Telegram bot service (research, approvals, voice intake, render, Buffer queue, analytics)
    web                 the dashboard (http://localhost:8090)
    check               what is configured and what is missing (no secrets printed)
    youtube-auth        connect YouTube statistics (read-only browser consent, once)
    instagram-connect   connect Instagram statistics (read-only; paste a token from Graph API Explorer, once)
    refresh-analytics   fetch statistics now
    new [topic]         queue a new idea (same as /new in Telegram)
    download-model      download + verify the Uzbek speech model into models/ (the installers run this)
    dry-run on|off      test mode on this computer (off: approved reels really go into Buffer's queue)
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys

from .config import load_settings, set_local_value
from .logging_setup import setup_logging

log = logging.getLogger("socialauto")


def cmd_run(settings, config_path=None) -> int:
    import threading

    from . import runner
    from .analytics.collector import make_collector
    from .app import build_app
    from .telegram_bot import TelegramBot
    env_path = settings.root / ".env"
    if not runner.ready(settings):            # first start: wait for the Setup page instead of exiting
        settings = runner.wait_for_token(lambda: load_settings(config_path))
    app = build_app(settings)
    try:
        moved = app.workflow.content.adopt_old_reels()     # Task 07: reels/ leaves the code folder
        if moved:
            log.info("Moved %d old reel folder(s) into the content repo", len(moved))
    except Exception:                         # noqa: BLE001
        log.exception("Could not move old reels into the content repo")
    if app.workflow.content.is_existing():    # Task 09: his repo is cloned (or synced) in the background at start
        app.workflow.content.prepare_async()
    collector = make_collector(settings, app.db, app.kv, app.clock)
    bot = TelegramBot(app, collector)
    from .netcheck import wait_until_online
    from .updater import RESTART_FILE
    watcher = runner.EnvWatcher(env_path, bot.request_stop, also=(settings.root / RESTART_FILE,))
    watcher.start()
    wait_until_online(log=log)                # after a boot the network may come later: wait quietly
    if watcher.changed:                       # settings changed while waiting: start fresh with them
        return runner.RESTART_CODE
    stop_claude = threading.Event()

    def claude_checks() -> None:              # one alert if Claude is missing / logged out; re-checked every 30 min
        while True:
            try:
                runner.claude_alert(app)
            except Exception:                 # noqa: BLE001
                log.exception("Claude status check failed")
            if stop_claude.wait(1800):
                return
    threading.Thread(target=claude_checks, name="claude-check", daemon=True).start()
    log.info("Starting the bot (dry_run=%s; approved reels go into Buffer's queue, Buffer posts them)", settings.dry_run)
    try:
        bot.run()
    finally:
        stop_claude.set()
        watcher.stop.set()
    return runner.RESTART_CODE if watcher.changed else 0


def cmd_web(settings) -> None:
    from .web.server import serve
    if not settings.dashboard_password:
        log.warning("DASHBOARD_PASSWORD is not set in .env: nobody can log in until it is")
    serve(settings)


def cmd_check(settings) -> int:
    import shutil

    from .claude_client import ClaudeClient
    ok = True

    def line(good: bool, text: str) -> None:
        nonlocal ok
        ok = ok and good
        print(("  ✔ " if good else "  ✘ ") + text)
    print("Social Automation — check")
    line(True, "mode: " + ("DRY-RUN (nothing is sent to Buffer, only recorded)" if settings.dry_run
                           else "LIVE (approved reels go into Buffer's queue; Buffer posts them)"))
    line(bool(settings.buffer_api_key), "Buffer API key in .env (queue, statistics)")
    line(bool(settings.telegram_token), "Telegram bot token in .env")
    line(bool(settings.allowed_user_ids), "Telegram allowed user id(s) in .env")
    line(bool(settings.dashboard_password), "dashboard password in .env")
    status = ClaudeClient(settings.claude, settings.claude_workdir).auth_status()
    line(bool(status.get("loggedIn")), f"Claude Code logged in (config dir {settings.claude.config_dir}, "
                                       f"{status.get('subscriptionType') or status.get('authMethod') or 'unknown'})")
    line(bool(shutil.which("ffmpeg")), "ffmpeg installed")
    yt_secret = settings.resolve(settings.youtube.client_secret_file).exists()
    yt_token = settings.resolve(settings.youtube.token_file).exists()
    line(yt_token, f"YouTube connected{'' if yt_token else (' (client secret present: run youtube-auth)' if yt_secret else ' (owner step)')}")
    ig = settings.resolve(settings.instagram.token_file).exists()
    line(ig, "Instagram connected" + ("" if ig else " (owner step: instagram-connect)"))
    line(bool(settings.meta_app_id and settings.meta_app_secret), "Meta app id/secret in .env (token auto-refresh)")
    from .platforms.tunnel import TunnelError, cloudflared_binary
    try:
        cloudflared_binary(settings.root)
        line(True, "cloudflared installed (temporary public links for Buffer)")
    except TunnelError:
        line(False, "cloudflared missing (optional): run the installer again")
    return 0 if ok else 1


def cmd_youtube_auth(settings) -> None:
    from .platforms.youtube import YouTubeStats, authorize
    secret = settings.resolve(settings.youtube.client_secret_file)
    token = settings.resolve(settings.youtube.token_file)
    authorize(secret, token)
    channel = YouTubeStats(secret, token).channel()
    set_local_value(settings.root, "youtube", "expected_channel_id", channel["id"])
    print(f"YouTube statistics connected (read-only): {channel['snippet']['title']}.")


def cmd_instagram_connect(settings) -> None:
    from .platforms.instagram import connect
    if not (settings.meta_app_id and settings.meta_app_secret):
        sys.exit("Put META_APP_ID and META_APP_SECRET into .env first (docs/OWNER_TODO.md).")
    token = getpass.getpass("Paste the token from Graph API Explorer (it is not shown): ").strip()

    def choose(pages):
        for i, p in enumerate(pages, start=1):
            print(f"  {i}. {p.get('name')} → @{p['instagram_business_account'].get('username', '?')}")
        k = input("Which one? [1]: ").strip() or "1"
        return pages[int(k) - 1]
    info = connect(token, settings.meta_app_id, settings.meta_app_secret, settings.instagram.graph_version,
                   settings.resolve(settings.instagram.token_file), choose=choose)
    print(f"Instagram statistics connected (read-only): @{info['username']} (Page: {info['page_name']}). "
          "The token renews itself automatically.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m socialauto")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "web", "check", "youtube-auth", "instagram-connect", "refresh-analytics", "download-model"):
        sub.add_parser(name)
    p_new = sub.add_parser("new")
    p_new.add_argument("topic", nargs="*")
    p_dry = sub.add_parser("dry-run")
    p_dry.add_argument("state", choices=["on", "off"])
    args = parser.parse_args(argv)
    if args.cmd == "download-model":                # before settings: works on a brand-new install
        from .model_download import download
        s = load_settings()
        return download(s.resolve(s.reel.stt_model))
    if args.cmd == "dry-run":                       # this computer's own setting (config.local.toml)
        s = load_settings()
        set_local_value(s.root, None, "dry_run", args.state == "on")
        print(f"dry_run = {'true' if args.state == 'on' else 'false'} saved in config.local.toml. "
              "Restart the bot and the website to apply it.")
        return 0
    settings = load_settings()
    setup_logging(settings.logs_dir, filename="web.log" if args.cmd == "web" else "socialauto.log")
    if args.cmd == "run":
        return cmd_run(settings)
    elif args.cmd == "web":
        cmd_web(settings)
    elif args.cmd == "check":
        return cmd_check(settings)
    elif args.cmd == "youtube-auth":
        cmd_youtube_auth(settings)
    elif args.cmd == "instagram-connect":
        cmd_instagram_connect(settings)
    elif args.cmd == "refresh-analytics":
        from .analytics.collector import make_collector
        from .app import build_app
        app = build_app(settings)
        alerts = make_collector(settings, app.db, app.kv, app.clock).refresh(force_reports=True)
        print("done" + (f"; problems: {[a[0] for a in alerts]}" if alerts else ""))
    elif args.cmd == "new":
        from .app import build_app
        app = build_app(settings)
        print("queued" if app.workflow.request_new(" ".join(args.topic) or None) else "an idea is already being written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
