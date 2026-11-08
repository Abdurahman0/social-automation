# Task 01: build the Social Automation project from zero

Read `CLAUDE.md` first. Its laws apply to everything here. Work in the project folder `social-automation` (empty repo:
`git init` it). Finish everything below fully and autonomously. The owner only reviews and approves.

## Reference
`~/youtube-automation` (the `ytauto` package) is the owner's working YouTube bot. **Read it before you design
anything**, then reuse its proven parts by copying them into this repo (never edit that repo). The parts:
the Claude CLI client + usage ledger + limit/reset parsing, the Telegram approval flow with versioned buttons,
Kokoro TTS, synced captions, FFmpeg pipeline + validation, thumbnails, slot calendar (DST-safe), outbox,
restart recovery, duplicate-upload guard, YouTube OAuth + upload + status check, lessons store.

## What the product does
1. **Ideas → script.** Claude proposes a video idea and writes the full script.
2. **Approval 1 (Telegram):** the bot sends the owner the **full transcript** (what will be said) plus a short
   **"What this video is about"** summary (topic, hook, target viewer, length, planned title, hashtags).
   Buttons: Approve / Reject / Regenerate / Edit (owner types a note, Claude rewrites).
3. **Make it.** After approval: the **owner's own uploaded voice** (see `docs/TASK_02_OWNER_VOICE.md`; no Kokoro narration), visuals, burned-in captions, music, render the
   vertical 1080×1920 video (≤ 60 s by default so it fits both YouTube Shorts and Instagram Reels),
   and a **thumbnail/cover** (1080×1920 cover for Reels + 1280×720 for YouTube).
   Run a quality gate (duration, audio levels, caption sync, black frames, thumbnail text readable).
4. **Approval 2 (Telegram):** the finished video + both thumbnails + final title/caption/hashtags.
   Approve → post. Reject / Regenerate / Edit as above. (Config switch `final_check = true` by default.)
5. **Post to both platforms** at the next free slot (or "Post now" button):
   - **YouTube:** Data API v3 upload (private + `publishAt` scheduling, custom thumbnail, verify it went public).
   - **Instagram:** official **Instagram Graph API** content publishing as a **Reel** (Business/Creator account
     linked to a Facebook Page, Meta app, long-lived token with auto-refresh). The API needs a public video URL:
     serve the file temporarily via a free Cloudflare quick tunnel (`cloudflared`) or similar free method, delete
     the link after publishing. Set the cover (`cover_url` / thumb offset), caption + hashtags. Poll the
     container status until `FINISHED`, then publish; verify the permalink.
   - No unofficial/private Instagram APIs or password logins (account-ban risk).
   - One platform failing must not block or duplicate the other; retry with back-off; idempotent.
   - Then send the owner both links in Telegram.
6. **Website: live analytics dashboard** (local, e.g. `http://localhost:8090`, protected by a login password
   from `.env`):
   - Overview: followers/subscribers, total views, reach, engagement rate, growth (day/week/month), for each
     platform and combined.
   - Per-video table + detail page: thumbnail, title, posted time, views, likes, comments, shares, saves,
     watch time / average view duration, retention where the API gives it, YouTube vs Instagram side by side.
   - Charts over time (views, followers, engagement), best posting times, top videos, comparison YouTube vs
     Instagram.
   - "Live": refresh on a schedule (respect API quotas; cache in the DB; show "updated N min ago"). Store daily
     snapshots so history charts work even where the API gives only current totals.
   - Pipeline view: what is waiting for approval, being made, scheduled, posted.
   - Data sources: YouTube Data API + **YouTube Analytics API**; Instagram Graph API **Insights** (account +
     media). Read the current official docs (WebSearch/WebFetch) for metric names, since they change.
   - Before accounts are connected the dashboard shows a clean "Connect YouTube / Connect Instagram" state with
     steps, never fake numbers.
   - Stack: your choice, but keep it light on memory (for example FastAPI + a built static frontend). Follow
     the UI law.
7. **Telegram commands:** `/status`, `/queue`, `/new` (make a video now, optional topic), `/pause` `/resume`,
   `/stats` (short summary + dashboard link), `/lessons`, `/usage`.

## Defaults decided for the owner (change only if the owner says)
- Folder/package: `social-automation`, Python package `socialauto`, own venv, SQLite DB.
- **Niche:** configurable in `config.toml` (`[content] niche`, style, language, length). Default niche until the
  owner picks: "surprising facts & mini-stories" in English, 30-45 s, one video per day at 19:00 Tashkent.
  Write the niche/style prompts so changing the niche is one config line.
- Visuals: free only (reuse the ytauto image/visual approach that works best and is free; no paid image APIs).
- Claude: Claude Code CLI on **account 1** (`~/.claude`, default config dir). Own usage ledger. No API key.
  Do NOT use account 2 (`~/.claude-youtube`).
- A NEW Telegram bot (its own token from @BotFather) and its own systemd **user** unit
  `social-automation.service` (+ one for the website). Don't reuse the YouTube bot's token.
- `dry_run = true`: "posts" go to `data/dryrun_posts.json`; everything else runs for real.

## Owner-only steps → `docs/OWNER_TODO.md` (short, numbered, Uzbek, click by click)
BotFather token; which YouTube channel (new or existing) + Google OAuth consent; Instagram Business/Creator
account + Facebook Page + Meta app + token; niche choice; switching `dry_run` off; GitHub repo for the push.
Prepare everything else so each step is just "paste this / click this".

## Done means
- Tests (pytest) for: approval flow + buttons, idempotent dual posting (fake YouTube + fake Instagram clients),
  partial failure retry, scheduling, quality gate, analytics fetch + snapshot math, dashboard API, auth/expired
  handling. All pass.
- A real end-to-end dry-run demo: idea → transcript approval message → real rendered video + both thumbnails →
  final approval → dry-run posts to both. Save proof to `proof/`
  (`demo.mp4`, `thumb_youtube.jpg`, `cover_instagram.jpg`, Telegram message screenshots or text,
  dashboard screenshots on phone + desktop width, `REPORT.md`).
- Dashboard checked visually on phone and desktop widths (Playwright, workers=1, memory-capped). No layout bugs.
- `README.md` (setup, how it works), `docs/DECISIONS.md`, `docs/OWNER_TODO.md`.
- Everything committed to git in small commits. No secrets in git.
- Final `proof/REPORT.md` in Uzbek: what works, what is waiting for the owner (only OWNER_TODO items), how to run.
