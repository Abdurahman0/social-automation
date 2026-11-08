# TASK 07 — Every user runs their own copy with their own accounts; nobody can touch the owner's repo

Owner (2026-11-08, voice): "I push this project to GitHub, my friend installs it and sees the website. It runs on
HIS computer always, when the computer turns on and connects to the internet. HE puts the Telegram bot token,
Instagram login, YouTube login, Claude login — everything is done inside the website. When they post something,
the website shows THAT user's own GitHub: his things go to his own repo. It must not affect my repo. Nobody can
write or post anything to my repo. Only I can push; everybody can get the project from my repo."

Builds on TASK_06 (Setup page, Settings page, install.sh / install.ps1). Inspect TASK_06_REPORT.md and the current
code first. All laws in CLAUDE.md still apply: the bot NEVER posts/publishes anything (Buffer = drafts only, the
owner's own cover), handmade UI controls only, never raw JSON / codes / ids in the UI, works on phone/tablet/desktop
in light and dark, stepper circles always have icons, OOM limits (systemd-run MemoryMax=3G for browsers/tests).
Finish everything; decide defaults yourself; no questions unless truly owner-only.

## 1. Code repo vs content repo (the core fix)
- Today `publish_git` commits reels into THIS repo and pushes to `origin` = `Abdurahman0/social-automation`. On a
  friend's computer that is the owner's repo. Change it:
  - The code repo (`origin` = owner's repo) is ONLY used to download updates (fetch/pull). The app never commits
    or pushes content to it. Add a hard guard + test: content push to a remote whose URL is the upstream code repo
    is refused, on every computer, including the owner's.
  - Content (reels/, videos, covers, scripts, research, sources) goes to a separate **content repo** in the
    user's OWN GitHub account, in a separate local folder (e.g. `data/content-repo/`), git-ignored by the code repo.
    Default repo name `social-automation-content`, private, created by the app if it does not exist.
  - The owner gets the same: his content goes to `Abdurahman0/social-automation-content` (private), not to the
    code repo. Move anything already under `reels/` locally into the content repo. Verify the code repo's history
    on GitHub contains no reels/video/voice files; if any, remove them from history before step 5.
- Never force-push anywhere. Pushing content is the user's own repo only — it is not "posting" to a platform.

## 2. Logins inside the website (Setup + Settings), each a stepper step with an icon and a "Tekshirish" check
- **GitHub**: "Connect GitHub" using GitHub's OAuth **device flow** (the page shows the short code + opens
  github.com/login/device; no password typed into our site). Fallback: paste a fine-grained personal token with a
  link explaining exactly which permissions (only the content repo, Contents read/write). Show the connected account
  (avatar + @login + link to the content repo), never the token. The token is stored only locally (secrets/, 0600).
  Disconnect button. If the user skips GitHub, content stays local and the site says so in plain words.
- **Claude**: the user logs into HIS OWN Claude account from the website: a button that runs the Claude CLI login
  flow for this computer and shows the login link/code in the page, then the status (logged in as …). No API key.
  If the CLI is missing, show how to install it for this OS.
- **Instagram / YouTube**: the bot never posts, so these logins are for drafts and analytics only:
  - Drafts: through the user's own Buffer account (already in Setup) — show which Instagram / YouTube / LinkedIn
    channels his Buffer has connected, with names and avatars, and a link to connect more in Buffer.
  - Analytics: "Connect Instagram" (Meta login, the user's own Meta app keys from Setup) and "Connect YouTube"
    (Google OAuth, read-only analytics scope, the user's own Google OAuth client — a guided step with screenshots
    explains how to make one). Show the connected account name, never tokens. Each one optional and skippable.
- **Telegram bot token + ID**: already in Setup; keep it.
- Every secret: only on this computer, masked after save, changeable in Settings. Never in git, never in logs.

## 3. Always running on the user's computer
- Starts when the computer turns on, even before anyone logs in where the OS allows it (Linux: user service +
  `loginctl enable-linger`; macOS: LaunchAgent; Windows: Task Scheduler at startup). Waits for internet and
  retries quietly; the site shows a clear "Internet yo'q — kutyapman" state instead of errors. Survives restarts.
  Verify on Linux with a real reboot simulation (stop/start the service, cut network) and write it in the report.

## 4. Updates from the owner's repo (read-only for everyone)
- Settings page: "Yangilanish bor" when the owner pushed something new; one button updates (fetch + fast-forward
  only, keeps the user's .env, secrets/, data/ and content repo untouched, restarts the service). Never pushes.

## 5. Owner's repo is read-only for everyone else
- On GitHub `Abdurahman0/social-automation`: no collaborators; protect `main` (no force-push, no deletion).
  Write in README: "Bu repoga faqat egasi yozadi. O'zingizniki uchun fork qilishingiz shart emas — o'rnating va
  o'z GitHub'ingizni ulang." Others can only open issues / forks; forks never touch the owner's repo.
- The owner said "everybody can get that project from my repo", so after steps 1-4 are merged and a final scan
  shows no secrets, no personal paths, no reels/voice/video files, no proof/ folder and no posting code in ANY
  commit of history: make the repo **public**. Report the scan result.

## 6. Tests and proof
- Unit tests: content push refuses the upstream code repo URL; content goes to the content repo; update is
  fast-forward only and never touches user data; secrets never appear in logs/HTML.
- Fresh clone into a temp folder as a fake second user (different HOME, different GitHub test repo is NOT needed —
  use a local bare repo as "his GitHub" to prove content lands there and the owner's repo is never written).
- Screenshots of every new Setup/Settings step on phone/tablet/desktop, light and dark → docs/proof (not pushed if
  proof/ is excluded; put the ones for the report in /tmp/social_task07/).
- Report in Uzbek: docs/TASK_07_REPORT.md (what changed, what the owner must do, Windows/macOS checked only by code).
- Commit, push to the owner's repo (SSH), confirm local == GitHub.

## 7. ADDENDUM (owner, 2026-11-08): clone must NEVER ask for the owner's login — finish everything
The owner tried to install on Windows and `git clone` asked to log into HIS GitHub account. That is wrong.
- Making the repo **public** is REQUIRED (not optional) as the last step of this task, after the full history scan
  in step 5. If the scan finds anything (secrets, personal paths, reels/voice/video, proof/, posting code) in ANY
  commit: rewrite history clean (fresh orphan history is fine), force-push once, re-scan, then make it public.
  The owner already approved making it public — do not ask again.
- Prove anonymous access with NO credentials at all: `GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false
  git -c credential.helper= clone https://github.com/Abdurahman0/social-automation.git /tmp/anon-clone` must succeed,
  and `curl https://api.github.com/repos/Abdurahman0/social-automation` must return 200 without a token.
- One-line installers that need no git login and no GitHub account:
  - Windows (PowerShell): `irm https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.ps1 | iex`
    — the script itself installs Git if missing, clones over public HTTPS into %USERPROFILE%\social-automation,
    then continues the install. Same for Linux/macOS with `curl -fsSL .../install.sh | bash`.
  - Put these one-liners at the top of README.md (Uzbek + English).
- The in-app updater ("Yangilanish bor") fetches anonymously over public HTTPS — never needs the owner's credentials,
  and has no push remote to the owner's repo at all.
- The user's OWN GitHub (content repo) login happens only inside the website (device code), never during install.
- Nothing partial: finish steps 1-6 fully, then this step, then report in docs/TASK_07_REPORT.md with the anonymous
  clone output and the exact Windows one-liner for the owner.
