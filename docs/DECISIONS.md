# Decisions

Decisions taken for the owner (laws in CLAUDE.md; tasks in docs/TASK_01_BUILD.md and docs/TASK_02_OWNER_VOICE.md).
Each can be changed; the config line or file is named.

## Owner's voice (law 14, Task 02)
- **Claude:** Claude Code CLI, account 1 (`~/.claude`), `--safe-mode --effort medium`, empty sandbox, web search only
  for research; usage ledger + one pause on a usage limit with the reopen time in Tashkent time; no API key (law 8).
- **No TTS in real videos.** Kokoro is only a dev dependency that makes `tests/fixtures/sample_voice_*.wav`.
- **Cleanup chain:** silence trim at both ends → highpass 80 Hz / lowpass 12 kHz → `afftdn` light denoise →
  two-pass `loudnorm` to −14 LUFS, −1.5 dBTP. No pitch or other effects.
- **Transcription:** faster-whisper `base`, int8 on CPU (~150 MB model, a few seconds per 40 s clip). The audio is
  decoded by our own ffmpeg (faster-whisper's PyAV path broke with the installed PyAV). Captions come from the
  transcription of the *cleaned* file that goes into the video, so they are in sync by construction; the gate still
  measures it.
- **Comparison:** word alignment (difflib) against the approved script. Ask the owner when coverage < 75 %, a run of
  6+ script words is missing, or the take is longer than 59 s / shorter than 3 s. "Continue" with a slightly long
  take speeds it up at most 1.15× (atempo, pitch kept); longer takes must be re-recorded.
- **Routing:** exactly one video waiting → assigned automatically; otherwise buttons (newest first) plus
  "make a new video from this voice". The newest voice wins and supersedes older renders/approvals.
- **Reminder:** one reminder ~3 h before the slot, ever, per video; then quiet slot moves.

## Analytics + dashboard
- Totals every 30 min (≈3 YouTube quota units), reports every 6 h (YouTube Analytics day + per-video + retention;
  Instagram day insights). Metric names per the 2026 docs (`views`, not the removed `impressions`/`plays`).
- Daily snapshots (one row per platform per Tashkent day) make history charts work where APIs only give totals;
  where the platform reports day values those win, and unreported newest days stay empty (no guesses).
- Engagement = (likes + comments + shares + saves) / views. Growth = now − snapshot N days ago (shown "—" until that
  much history exists).
- FastAPI + hand-written HTML/CSS/JS (no build step, ~60 MB RAM). HMAC-signed HttpOnly SameSite=Strict cookie, login
  rate limit. Dark theme; platform colours validated for colour-blind safety (YouTube #e66767, Instagram #9085e9).
  Handmade date-range picker, select and checkbox. Before accounts are connected: connect cards with steps, no numbers.
- Visual QA: `scripts/screenshots.py` (Playwright, installed Chrome, one worker, memory-capped) checks phone/tablet/
  desktop for horizontal overflow, overlapping cards, console errors and text contrast. Layout-test screenshots use a
  temporary fixture database and are stored separately (`proof/layout-test/`); the real dashboard never shows fixture
  data.

## Operations
- Two systemd **user** units (`social-automation.service` capped at 3 GB, `social-automation-web.service` at 600 MB).
- SQLite (WAL) in `data/`; jobs and outbox are durable; on start, running jobs are re-queued and any video whose next
  step was lost is resumed.
- Secrets only in `.env` and `secrets/` (chmod 600, gitignored); logs redact Telegram/Google/Meta tokens.

## Task 04 — the owner's reel flow (the only pipeline since Task 05)
- **Kept:** Telegram approvals with versioned buttons, the owner's voice intake, the analytics site, dry-run, lessons.
  (The earlier English "facts" flow was removed in Task 05: it could not work without posting.)
- **Research:** Buffer statistics (personal API key; averages of views/shares/comments/averageTimeWatched) + Claude with
  WebSearch/WebFetch. Topics are kept only when in scope (water/wastewater word list), sourced (every fact has an http
  source) and not similar to the last 30 posts or earlier research files (token overlap ≥ 0.5 = duplicate).
  `research/<date>-<topic>.md`, 3–5 topics strongest first; the owner picks one (or "boshqa mavzular").
- **Script:** 8 parts (hook · lead · body1 · loop1 · body2 · loop2 · body3 · cta), 45–60 s at 2.2 words/s for Uzbek,
  `key_fact` must appear in the first 5 s of words, every listed term must be followed by "ya'ni" within ~140
  characters. One corrective redraft; failures become lessons. The owner can paste a full edited script (≥ 40 words
  = replacement, split by labels or blank lines, else Claude splits it without changing words).
- **B-roll:** real footage/photos only. Wikimedia Commons (no key; CC0/PD/CC BY/CC BY-SA only, NC/ND refused) and Pexels
  / Pixabay when their free keys are set. Titles that suggest animation/3D/maps/illustrations are refused. Mixkit has no
  API (not scraped); UzA needs permission (not used). Source + licence per clip in `broll/sources.json` + SOURCES.md.
  Work folder `~/MediaBuffer/_work/<date>-<topic>/` (configurable, outside cloud-synced folders).
- **Design:** Remotion 4 composition (`remotion/`): real media with slow moves, infographic card, title at the top,
  subtitles at eye level with the current word highlighted. Text boxes are computed in Python (`reel/layout.py`) and
  passed to Remotion, so the safe-zone check (nothing in the bottom 20 %, nothing under the 150 px right-side buttons,
  subtitles centred at 45–68 % height) measures exactly what is drawn. Remotion renders silent (concurrency 2, 3 GB
  cap); ffmpeg muxes the audio.
- **STT + alignment:** NavaiSTT v1 was withdrawn by its author; its successor **rubaiSTT v2** (Whisper-medium for Uzbek,
  Apache-2.0, WER ~17 %) runs locally as a CTranslate2 int8 build through faster-whisper. The voice is split at pauses
  (silencedetect, ≤ 25 s chunks), transcribed with word timestamps, and aligned to the approved script (Cyrillic →
  Latin, apostrophes unified, word-level sequence alignment, interpolation by word length). The MMS forced aligner was
  rejected (CC-BY-NC weights); wav2vec2-uz CTC aligners need PyTorch (~2 GB RAM) — not worth it since the text is known.
- **Voice chain:** trim → highpass 80 Hz → light denoise → compressor (−20 dB, 3:1) → loudnorm; music ducks under the
  voice (sidechain); final −14 LUFS.
- **Versions:** `exports/<date>-<topic>_vN.mp4`; N comes from existing files and a marker, so a number is never reused.
- **Checklist:** `docs/reel-mistakes-checklist.md` = fixed rules + lessons, rewritten on every render; checked before
  (script rules, B-roll licences/realness, safe zones, text fit, voice length/coverage) and after (format, loudness,
  peak, sync, black frames, and the 8 section-boundary frames: not black/flat/blurry). A failure re-renders (new
  version) and is recorded as a lesson.
- **Fixes:** the owner's fix note (text, or a voice note transcribed with rubaiSTT) → Claude turns it into a plan (new
  B-roll words / infographic / title / subtitle spelling per part) → only those parts get new footage → `_v(N+1)`.
- **Cover:** never made by the bot (law 16); after approval the bot asks for it in Telegram.
- **Publishing:** `reels/<date>-<topic>/` (video, cover, research, script, sources) committed with `git commit -- <paths>`
  (never sweeps other changes), Git LFS for files > 50 MB (`bin/git-lfs`), pushed to `main` only when a remote exists
  (no force). Buffer drafts (`createPost`, `saveToDraft: true`, `mode: addToQueue`, no `dueAt`) for Instagram (reel),
  YouTube (title, category 27) and LinkedIn; captions in the owner's style (style file learned from previous Buffer
  posts). Buffer fetches the video from a temporary Cloudflare quick-tunnel URL. While `dry_run` is on, drafts go to
  `data/dryrun_posts.json` only.
- **Live + story:** every 15 min the bot checks Buffer for the Instagram draft becoming `sent` (with `externalLink`).
  Then a Buffer story draft (the cover image, the link in the reminder sticker field — Buffer has no link-sticker field
  and Instagram's API cannot publish link stickers) and a Telegram message with the image, link and one-line
  instructions; "Storyni joyladim" closes the reel.
- **Naming:** everything is named by the publish date; when it changes (a quiet slot move) `rename_all` moves the work
  folder, all exports, the research file and the `reels/` folder (git mv when tracked) and the YouTube draft title is
  edited in Buffer.
- **Demo voice:** Kokoro has no Uzbek voice; the demo's stand-in narration is made with the espeak-ng library's Uzbek
  voice (`scripts/make_test_voice_uz.py`, saved as `tests/fixtures/sample_voice_*.wav`). Real reels use only the owner's
  recordings.

## Task 05 — the bot never posts, the bot never makes covers (owner laws 15 and 16)
- **Removed, not disabled:** the direct YouTube/Instagram posting path (`publishing/publisher.py`, uploads, the Instagram
  container/publish calls, `publish_direct`, the "Hozir joylash"/"vaqtida" buttons, `post_now`, slot booking, the
  posts tables), the bot-made thumbnails (`video/thumbnails.py`), the AI-image renderer of the facts flow
  (`video/render.py`, `video/images.py`, `video/captions.py`, `content.py`) and the facts flow itself (it existed only
  to post). `owner_reel` is the only flow; `workflow.py` is that flow.
- **Read-only platform clients** (`socialauto/platforms/`): YouTube with `youtube.readonly` + `yt-analytics.readonly`
  only; Instagram GET-only with `instagram_basic`, `instagram_manage_insights`, `pages_show_list`,
  `pages_read_engagement`. They feed the dashboard; nothing else.
- **Buffer:** `draft_input()` is the only createPost input; `saveToDraft: true` is set last and cannot be overridden
  (not even by metadata), no `dueAt`, no share/schedule modes, no delete. `editPost` is refused unless the post is still
  a draft. Live detection only reads post status.
- **Cover:** the owner's file is copied byte for byte (JPEG/PNG); any other image format is converted to PNG (pixels
  unchanged) and the owner is told. No fallback: without a cover the reel waits at "Muqova kutilmoqda". The story draft
  uses the owner's cover. Remotion/ffmpeg never add a cover frame.
- **Database:** an idempotent migration drops the posting tables and the bot-cover / post-now columns from old
  databases; fresh databases never have them.
- **Guard tests** (`tests/test_guards.py`): the code (Python, scripts, Remotion, website) is scanned for upload /
  publish / schedule endpoints and cover generators; every Buffer create is checked to be a draft.
- **Wording:** Telegram, the website and the docs say "Buffer'da qoralama tayyor — tasdiqlab rejalashtirish sizda";
  dry-run now only means "the Buffer drafts are only recorded locally".

## Task 06 — GitHub, and an app anyone runs on their own computer
- **Setup page** (`/setup`, `socialauto/web/setup.py`, `socialauto/env_store.py`): the first start (no dashboard
  password) sends every page to the wizard; before a password exists it answers only requests from this computer
  (127.0.0.1/::1 and *not* relayed — a request carrying `X-Forwarded-For`/`Forwarded`/`CF-Connecting-IP`/`X-Real-IP`
  is treated as remote, because a tunnel or proxy also connects from 127.0.0.1). Afterwards the same pages need the
  password ("Sozlamalar"). Values go to `.env` atomically (temp file + replace), one line each (a value cannot add a
  line), chmod 600 / user-only ACL on Windows, and come back only masked (`ab••••••yz`; user ids and the Meta app id
  are not secrets and are shown). The Telegram check sends the token only to api.telegram.org (`getMe`), the Buffer
  check only to Buffer; a malformed token is refused before any network call.
- **Bot service lifecycle** (`socialauto/runner.py`): no token → it waits and re-reads `.env` every 5 s instead of
  exiting; `.env` content changes → it stops polling cleanly and exits with code 75; systemd `Restart=always`,
  launchd `KeepAlive` and the Windows wrapper loop (`scripts/windows_service.ps1`) start it again. Claude missing or
  logged out → one owner alert ("owner_action", law 5), repeated only after Claude worked in between; re-checked every
  30 minutes; jobs wait (nothing crashes).
- **Installers** (`install.sh`, `install.ps1`): idempotent, also the updater. The service files are *generated* with
  the clone's own path (no hard-coded owner path; the old `systemd/` templates and `install_services.sh` are gone).
  Memory caps (law 9) only where they exist: `systemd-run` scopes for the heavy install steps and `MemoryMax` in the
  units on Linux; macOS/Windows rely on the existing low-memory settings (ffmpeg 2 threads, Remotion one tab).
  Missing Python/ffmpeg/Node: Homebrew (macOS) and winget (Windows) install them; on Linux the exact apt/dnf/pacman
  command is printed (no sudo from the script). cloudflared is optional and downloaded into `bin/`; Git LFS stays
  optional (only reels over 50 MB need it).
- **Speech model**: `python -m socialauto download-model` downloads rubaiSTT from its Hugging Face repository
  (progress bar) and verifies each LFS file against the SHA-256 the repository publishes; a mismatching file is
  deleted so the next run downloads it again. It is ~775 MB, not 1.2 GB (the int8 build).
- **Portability**: Windows names for `remotion.cmd` and `cloudflared.exe`; the Claude CLI is resolved with
  `shutil.which` (on Windows it is `claude.cmd`). A test fails if a tracked file contains this machine's home folder
  or user name.
- **GitHub**: private repo `Abdurahman0/social-automation`, pushed over SSH. The old history contained the removed
  posting code, the old proof files and owner paths, so `main` on GitHub starts from one clean squashed commit; the full
  history is kept only in the local branch `local-history`. `proof/` is untracked and ignored.
- **Reels push**: approved reels still go to `reels/<date>-<topic>/` in this repo (Task 04); now that a remote exists
  they reach the private GitHub repo. A clone without push rights keeps them locally and the website says so.

## Task 07 — every user runs their own copy with their own accounts; the code repo is read-only
- **Two repos.** Code repo (`origin`, the owner's `Abdurahman0/social-automation`): fetch + fast-forward only. Content
  repo (`data/content-repo`, ignored by the code repo): reels go there and are pushed to the user's own
  `<login>/social-automation-content` (private, created through the API after the GitHub login) or to a remote the
  user set in `config.local.toml` (the owner uses SSH: `git@github.com:Abdurahman0/social-automation-content.git`).
- **Hard guard** (`ContentRepo.guard`): before every content push the target is reduced to one canonical form
  (`github.com/owner/name` for https/ssh/git@/credential URLs, a resolved path for local repos) and refused if it
  equals the configured code repo, any remote of the code folder, or the code folder itself. Raised and logged, on
  every computer (the owner's too). `git push` exists only in `content_repo.py` (a test checks this). Never `--force`.
- **GitHub login:** OAuth app "Social Automation" (owner's account, device flow enabled; client id
  `Ov23liS94MsnZzPLrzTA` in config.toml — public by design, no secret is needed for the device flow). Scope `repo`
  (OAuth apps have nothing narrower that can create a private repo and push). The fallback fine-grained token can be
  limited to the content repo with Contents read/write; such a token cannot create repos, so the page links to
  github.com/new for that one repo. The token lives in `secrets/github.json` (0600 / user-only ACL) and reaches git
  only through the environment of the one push command (a credential helper reads `$SA_GH_TOKEN`), never argv/config.
- **Claude login on the website:** the site runs `claude auth login --claudeai` in a pseudo-terminal (pipes on
  Windows) for this computer's Claude config dir, shows the sign-in link, passes the pasted code, then reads
  `claude auth status` (email + plan shown). Tested against a throwaway config dir: link shown, a wrong code fails
  cleanly, the real login is untouched.
- **Instagram / YouTube** are read-only analytics logins (the bot never posts): Meta login with the user's own app
  (redirect `…/api/accounts/instagram/callback`), Google login with the user's own "Desktop app" client (redirect to
  the site root, loopback). The callback is authorised by a random single-use `state` (15 min), because the site's
  SameSite=Strict cookie is not sent on a redirect from facebook.com / google.com. Drafts still go through Buffer;
  the Buffer step lists the user's channels with names and avatars (falls back to the plain query if Buffer's schema
  has no avatar field, so drafts are never affected).
- **config.local.toml** (git-ignored) holds this computer's own settings (dry_run, content remote, YouTube channel id);
  config.toml stays exactly as in the code repo, so updates are always a clean fast-forward.
- **Updates:** `Updater` allows only fetch/rev-parse/rev-list/log/status/merge-base/diff and `merge --ff-only`.
  Diverged history or hand-edited tracked files → refused with a plain reason, nothing changed. After an update:
  pip / npm refresh only if their lists changed, `data/restart_request` restarts the bot (EnvWatcher), the website
  exits with 75 and its service manager starts it again.
- **Always on:** Linux user units + linger (start at boot, before login), `After=network-online.target`; the bot waits
  for internet quietly (`netcheck.wait_until_online`) and polling retries forever; the site polls `/api/net` and shows
  "Internet yo'q — kutyapman". Windows: the task registers with S4U + AtStartup when the installer runs elevated,
  otherwise AtLogOn (and says so). macOS: LaunchAgent (at login; a LaunchDaemon would need root).
- **Owner-only (GitHub sudo mode / 2FA):** making the code repo public, the `main` protection rule and the
  collaborator check — in docs/OWNER_TODO.md §15, with the history scan done first.
- **§7 addendum — no login to get the code.** The owner's Windows `git clone` asked for his login only because the
  repo was private. One-line installers (`irm …/install.ps1 | iex`, `curl -fsSL …/install.sh | bash`) bootstrap when
  there is no project folder yet: install Git if missing (winget / Homebrew or Command Line Tools / apt-dnf-pacman),
  clone over public HTTPS with `credential.helper=` and no terminal prompt (no Git Credential Manager window), set the
  push URL of `origin` to `no-push:the-code-repo-is-read-only`, then run the real installer from the clone. The
  PowerShell bootstrap uses `return`, never `exit` (exit would close the user's window under `iex`). The updater
  fetches with `credential.helper=` too. `SA_REPO_URL` / `SA_DIR` / `SA_BOOTSTRAP_DRYRUN` exist for mirrors and tests.
- Making the repo public, the `main` protection and the collaborator check need the owner's 2FA ("sudo mode") on
  GitHub — even authorising our own OAuth app for API use asks for it — so they are an owner step (OWNER_TODO §15),
  with `scripts/history_scan.sh` (clean) run first and `scripts/verify_public.sh` to prove anonymous access after.

## Task 08 — colour themes and the wave (2026-11-09)
- **Mode + palette are two separate choices.** `sa_theme` = `light | dark | system` (old saved `light`/`dark` keep
  working), `sa_palette` = `oltin` (default, the original yellow) / `okean` / `zumrad` / `lola` / `binafsha` / `shafaq`.
  Default mode is **Tizim** (it was "follow the OS when nothing is saved" before too). An inline script in
  `index.html` `<head>` sets `data-mode`, `data-theme` (resolved) and `data-palette` on `<html>` before the stylesheet,
  so a reload never flashes the wrong theme.
- **Tokens:** one block per palette x mode with the FULL token set, selected by attributes only
  (`[data-theme][data-palette]`), so a swatch can preview its own palette and the fallback wave can read the new
  `--bg` from a hidden probe. Oltin keeps the old values exactly. The other palettes tint every neutral (bg,
  surfaces, hairline, text) towards their hue; contrast (AA 4.5 for text and accent text, 3 for chart lines and
  status colours) is tested from the CSS in `tests/test_themes.py`. YouTube / Instagram colours are the same on every
  palette (recognisable); only the "Jami" line follows the palette's secondary text.
- **The wave:** View Transitions with a `clip-path: circle()` on `::view-transition-new(root)` from the centre of the
  clicked swatch dot / mode icon to the farthest corner, 720 ms, `cubic-bezier(.4, .15, .2, 1)` (a gentle gather, then
  a long soft ease-out; a sharper ease-out covered ~95 % of the screen in the first half and read as a flash, not a
  wave). The crest is a fixed overlay inside the new view (radial gradient on a registered `--wave-r`) so it rides
  just inside the circle's edge and fades out. Charts use `var(--yt)` etc. so they re-colour with no re-render; the
  switch no longer calls `route()`.
- **Second tap during a wave:** Chrome hit-tests every tap to `<html>` while a View Transition runs, even with
  `pointer-events: none` on `::view-transition`. A capture-phase handler finishes the running wave and hands the tap
  to the real control under the finger, so a second swatch starts a new wave from its own point and the popover
  stays open.
- **Fallback** (no View Transitions): a fixed circle of the new `--bg` grows (`clip-path`), the theme switches
  underneath, the circle fades in 260 ms. **Reduced motion:** a 180 ms cross-fade (View Transitions) or instant.
  "Tizim" follows OS changes live (cross-fade, no wave: there is no clicked point).
- **Proof** `scripts/theme_check.py` (56 checks). Playwright's own video recorder needs an extra download, so the
  GIF is built from frames of the frozen wave every 36 ms with the system ffmpeg (sharper and deterministic).

## Task 09 — connecting a user's existing content repo
- **Choice saved per computer** in `config.local.toml` (`content_mode`, `content_existing`); `ContentRepo` re-reads it
  on every call, so the website's choice reaches the running bot without a restart.
- **No repo is created at GitHub login any more** while nothing is chosen: the user picks «Yangi» (then the private
  repo is created) or «Mavjud» — so Javohir does not get an empty extra repo.
- **Partial + sparse clone** (`--filter=blob:limit=1m`, videos/audio excluded): his repo is ~630 MB, the clone ~50 MB.
  New reel files are added with `git add --sparse`.
- **Sync = fetch, then fast-forward or rebase; never --force.** A rejected push is fetched and rebased again (3 tries).
  On a conflict the rebase is aborted, our commit stays on `socialauto/kutilmoqda/<folder>`, main follows his history,
  and the next publish tries to cherry-pick it again.
- **His layout** is detected from the tree (`reels/<date>-<topic>/reel.mp4|cover.jpg`); a same-named folder of his
  is never overwritten (`<folder>-2`). He does not use LFS, so we don't either (only above GitHub's 100 MB limit, with a
  `.gitattributes` inside the reel folder so his root file is untouched).
- **posted.md** only after a real Buffer queue (not in dry-run), wording «Buffer navbatida», his column format read
  from the header line; a concurrent edit by him is handled by re-reading his file and appending again.
- **Brand rules** (brand/*.md without templates, guidance-book.md, brand/workflow skills) go into the system prompt of
  every research/script/caption call (Claude runs in safe mode, so the text is passed, not loaded as skills). The
  first "maksimum N s" found sets the length window to N−15…N (his: 30–45 s) for scripts, voice and video checks.

## Task 10 — every error to Telegram; «/new <idea>»
- **One reporter** (`socialauto/errors.py`) writes plain-Uzbek messages into the durable outbox (kind `error`, survives
  restarts). Reasons come from a cause map (no internet, timeout, Claude WebSearch / CLI, ffmpeg, speech model, B-roll
  keys, disk full, push rejected, checklist, no topics); anything else is one shortened line with tokens, keys, URL
  logins and long opaque strings removed and paths cut to the file name. Stack traces stay in the log.
- **No spam:** one message per job per distinct error code; a periodic problem (statistics, auto-update, startup
  checks, the loop) again only after it worked in between (or after 24 h). Offline = one «Internet yo'q» and one
  «qayta ulandi»; a connection error while `netcheck` says we are online is an ordinary job error, not "offline".
- **Research with zero usable topics gives up at once** (a retry returns the same thing) with the reason counted per
  filter (off-niche / duplicate / no source) and the buttons «🔄 Qayta urinish» and «🔎 Boshqa mavzu».
- **The idea is the main constraint of the prompt** (`research.prompt(..., idea)`), and the filters respect it: the
  owner's own idea is never in the "already covered" list (only chosen topics count), the idea's own words do not make
  two angles "the same topic", near-duplicates of earlier titles are dropped only above 0.85 similarity, and the niche
  check also reads the hook, «nega hozir» and the facts.
- **`/new` alone asks** «Qaysi g'oya bo'yicha?» (next message = the idea; `/skip` or «🎲 Bot o'zi tanlasin» = the old
  behaviour, the bot picks). `/new` while paused says so instead of «Tadqiqot boshlandi».
- **Stuck reels:** «allaqachon ketyapti» only while a research job is running or freshly queued; a research waiting
  to retry after an error gives way to the owner's new /new; RESEARCHING with no job is marked «To'xtab qoldi»;
  DRAFTING with no job gets its job back.
- **Watchdog:** limits per kind (research 20, render 60, publish 30, voice 20 min, others 30). A thread cannot be
  killed safely, so a stuck run is abandoned: the job is re-queued (the late finish is ignored by an attempts check on
  every queue update) and no second job of that kind starts while the stuck one is alive (memory).
- **Automatic updates in the bot** (`[github] auto_update = true`, every `update_check_hours`): fetch + fast-forward
  only (the same `Updater`), then `data/restart_request`; the website now watches that file too and restarts, so both
  run the new code. DB changes are migrations that run at start (`_add_idea`).
- **A stopped research is not restarted automatically** for 24 h (the owner has the button); otherwise a broken Claude
  would produce a stop message every hour.
