# Task 06: Publish to GitHub as an app anyone runs on their OWN computer (owner, 2026-11-08)

Owner, 2026-11-08: "If you put the project to GitHub, it should have places where I enter the bot token and other
things, but it should run on each user's local computer." Owner's answers to the follow-up questions:

| Question | Owner's answer |
|---|---|
| Which project | Only Social Automation (not `~/youtube-automation`, do not touch it) |
| Where tokens are entered | **(a)** A "Sozlash" (Setup) page on the website, shown on first start |
| Operating systems | Linux, **Windows and macOS** |
| Install | **(a)** One command: `./install.sh` (Linux/macOS), `install.ps1` (Windows) |
| Topic / language | **Do not touch for now.** Keep the owner's water/wastewater topic and Uzbek as they are |
| Script writer | Each user uses **their own Claude account** (Claude Code CLI login on their machine), no API key |
| GitHub | Owner's own account **`Abdurahman0`**, repo name **`social-automation`** (same as the folder) |
| Old demo / proof files | **Do not publish them.** `proof/` must not go to GitHub |

## Order
1. Finish TASK_05 (never post, owner makes the cover) and **merge it into `main` first**. The publish code must never
   reach GitHub, not even in history of the pushed branch. Then do this task on `main`. Commit in small steps.
2. `dry_run` stays on by default for every new install.

## 1. Setup page (first-run wizard) on the website
- On first start (no config yet) every page redirects to `/setup`. Handmade, beautiful, Uzbek UI, light + dark,
  phone/tablet/desktop (UI law: no raw JSON/codes/ids, handmade inputs, no layout bugs).
- Steps (stepper with icons, never empty circles): 1) Dashboard password  2) Telegram bot token + allowed user id(s)
  with a "Tekshirish" button that calls `getMe` and shows the bot's name  3) Buffer API key with a check button
  (shows the connected channels by name)  4) Optional: Meta app id/secret, Pexels, Pixabay keys  5) Claude: shows
  whether the `claude` CLI is installed and logged in on THIS computer, with plain instructions
  ("terminalda `claude` yozing va o'z akkauntingiz bilan kiring") and a re-check button  6) Summary + Start.
- Each step explains in one or two Uzbek sentences where to get the value (BotFather, @userinfobot, Buffer settings).
- Values are saved to the local `.env` (chmod 600 on Linux/macOS; user-only ACL on Windows). Secrets are never
  shown back in full (masked, "o'zgartirish" button), never logged, never sent anywhere except the service they
  belong to.
- After setup a "Sozlamalar" page lets the user change any value later. The bot restarts itself after a change.
- Before the dashboard password exists, `/setup` is only reachable from `127.0.0.1` (the server binds to localhost
  by default). After setup, setup changes need the password.
- `.env.example` stays as the documented manual alternative (README mentions it).

## 2. Runs on Linux, Windows and macOS
- Remove every hard-coded owner path (the owner's home folder, `~/Desktop/...`); use paths relative to the project or
  `platformdirs` user data dirs. A search for the owner's user name must return nothing in tracked files.
- Background running: Linux keeps systemd user services; macOS gets a `launchd` agent; Windows gets a Task
  Scheduler task (run at logon). All created by the installer, all removable by an uninstall command
  (`./install.sh --uninstall`, `install.ps1 -Uninstall`).
- The memory wrapper (`systemd-run ... MemoryMax`) is only used on Linux when available; other OSes fall back to
  plain subprocess calls with the existing low-memory settings (ffmpeg threads, Remotion one tab).
- ffmpeg, Node (for Remotion), Python 3.11+: the installer checks them and installs or tells the user exactly how
  (winget / Homebrew / apt). Remotion's browser download runs in the installer.
- rubaiSTT model (gitignored, ~1.2 GB): the installer downloads it from its official source into `models/` with a
  progress bar and checksum; the setup page shows its status.
- Telegram bot uses long polling (no public URL needed). cloudflared stays optional.

## 3. Installers
- `install.sh` (Linux + macOS) and `install.ps1` (Windows): create `.venv`, install requirements, install the
  Remotion npm packages, download the model, check `claude` CLI, register the background service, start it, and
  open `http://localhost:8090/setup` in the browser. Re-running is safe (idempotent) and works as an updater
  after `git pull`.
- Clear Uzbek + English messages at each step; on failure say what to do, no stack traces to the user.

## 4. Claude = each user's own account
- Keep using the Claude Code CLI. No Anthropic API key field anywhere. If `claude` is missing or logged out, the
  bot sends one Telegram alert and the setup/status page shows how to fix it; generation waits, nothing crashes.

## 5. Topic and language: unchanged
- Do not add topic/language options and do not change the water/wastewater prompts. Just make sure nothing in them
  contains the owner's personal paths or secrets.

## 6. GitHub repo
- Repo: `github.com/Abdurahman0/social-automation`, **private** (owner chose the account and name but not the
  visibility; private is the safe default, the owner can make it public later). Push over SSH
  (`git@github.com:Abdurahman0/social-automation.git`; the SSH key on this machine is already authenticated as
  `Abdurahman0`). `gh` is not installed: create the empty repo through the GitHub website using the owner's Chrome
  (`~/telegram-ai-agent/chrome_accounts.py`, find the Chrome profile that is logged in as Abdurahman0; read the
  script first, do nothing else in the browser). Do not add a README/licence on GitHub's side.
- Remove `proof/` from git tracking (`git rm -r --cached proof`, add `/proof/` to `.gitignore`); keep the files
  locally. Also keep out: `data/`, `logs/`, `work/`, `models/`, `secrets/`, `.env`, test voice of the owner if it is
  the owner's real voice (`tests/fixtures/sample_voice_demo_uz.wav` only if synthetic).
- **History check before the first push:** the owner's paths, old proof files, any secret, and the removed publish
  code must not be in the pushed history. If they are, push a fresh history (squash into a clean initial commit on a
  new branch, push that as `main`); keep the local full history in a local branch `local-history`. Run a secret
  scan (`gitleaks` or `git grep` for token patterns over all pushed commits) and include the result.
- README (Uzbek first, English below): what it is, requirements, one-command install for each OS with screenshots
  of the setup page, how to log in to Claude, how to update, how to uninstall, the "bot never posts" law.
- Update `CLAUDE.md` law 12 (remote now exists) and `docs/DECISIONS.md`.

## Proof (report in Uzbek, `docs/TASK_06_REPORT.md`, not in proof/)
- `pytest` green, plus new tests: setup page saves/masks values, first-run redirect, localhost-only before password,
  path code has no owner paths, installer scripts pass `shellcheck` / PowerShell parse check.
- Fresh-clone test on this Linux machine: clone into `/tmp`, run `./install.sh` (inside the memory cap), complete the
  setup page with dry-run values, screenshots (phone, tablet, desktop, light + dark) of every setup step.
- Windows/macOS cannot be run here: verify by static checks and say so plainly in the report.
- Repo link, pushed commit hash, secret-scan output.
