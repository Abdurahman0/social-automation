# TASK 09 — A user connects his EXISTING content repo (first user: github.com/eraliyev-j/the-suvyektiv-media)

Owner (2026-11-10): "He works just like our socials project. That's why I told you to add GitHub — he will connect
this repo." The user is Javohir (brand «Doktor H₂O», Instagram @suvyektiv, water science reels in Uzbek). Today he
makes every reel by hand with Claude Code in that repo. He will install Social Automation on his own computer, with
his own accounts (Task 07), and connect THAT repo as his content repo instead of a new `social-automation-content`.

All laws in CLAUDE.md apply (UI law, secrets, OOM limits, never post — Buffer only as today, owner's cover law,
the code repo is read-only for the app). Finish everything; decide defaults yourself; no questions.

**Never write to github.com/eraliyev-j/the-suvyektiv-media yourself.** Do not push, open issues/PRs or star it. For
tests, clone it (read-only) into a temp folder and use local bare repos as remotes.

## 0. Study his repo first (read-only clone into /tmp)
- `reels/<YYYY-MM-DD>-<topic>/`: `script.md` (voice text with seconds, sources, caption), `src/*.py` (per-reel
  render scripts), `reel.mp4`, `cover.jpg`, sometimes `reel_en.mp4`, `voice.m4a`.
- `posts/` carousels (`slides.json` + `tools/render.py`), `brand/voice.md`, `guidance-book.md`, `audits/`,
  `posted.md` (what was posted when), `.claude/skills/` (ig-* pack, effects, video-montaj, doktor-h2o-workflow,
  doktor-h2o-brand). Many mp4 files are committed directly (check whether he uses Git LFS; follow what he does).
Write what you found in `docs/TASK_09_REPORT.md` (short) before coding.

## 1. Connect an existing repo (website, Sozlamalar → GitHub)
- After the GitHub account is connected (device flow, as today), the user chooses: **«Yangi repo yaratish»**
  (today's behaviour) or **«Mavjud repomni ulash»**: a handmade searchable list of HIS repos (name, private/public
  badge, last update in Tashkent time; no ids, no raw JSON), plus a field to paste a repo link. Only repos he can
  push to are selectable; a repo without push rights shows a plain Uzbek reason.
- Saved per computer (config.local.toml / settings store), not in the code repo. The guard stays: the upstream
  code repo (and any remote of the code folder) is always refused.
- Switching repo later is possible; the old local clone is kept (renamed), never deleted.

## 2. Work on top of his history, never over it
- When an existing repo is chosen, **clone** it into `content_dir` (shallow/partial clone is fine if it is big;
  `git lfs` if the repo uses it). Do not `git init` a new history there.
- Before every publish: fetch, then fast-forward or rebase our new reel commit on top of his latest `main`
  (he also commits from his own computer). On conflict: stop, keep the reel locally, tell the user in Telegram in
  plain Uzbek; never `--force`, never rewrite or delete his files.
- Commit only the new reel folder (and the `posted.md` line, below). Never touch `.claude/`, `brand/`, `posts/`,
  `audits/`, `src/` of old reels, or anything else.

## 3. Follow HIS repo conventions when it is his repo
- Detect the layout from the repo (reels/<date>-<topic>/, file names `reel.mp4`, `cover.jpg`, `script.md`) and
  write new reels the same way; a repo with no recognisable layout keeps our default layout.
- `script.md` in his format: voice text with timings, sources (links/DOI), the caption.
- If `posted.md` exists, append a line in his exact format when a reel is approved into Buffer (never claim
  "posted" — Buffer queue/draft wording, matching what actually happened).
- His brand rules (`brand/voice.md`, `guidance-book.md`, project skills under `.claude/skills/`) are read and
  passed to Claude when generating his script/caption/research, so the output sounds like him (reel ≤ 45 s, numbers
  only from sources, his CTA). Read-only. The website «Ko'nikmalar» section already lists project skills — make
  it include the connected content repo's skills (label «Kontent reposi»).
- His past reels and `audits/` may be used as examples for the topic/hook suggestions (read-only).

## 4. Website and Telegram
- GitHub page: connected repo name (owner/name, link), branch, last sync, «N ta reel» count from his repo
  (including his manual ones), and «oxirgi yuklangan reel». Plain Uzbek, dark/light, all palettes, phone/tablet/
  desktop, no layout bugs.
- Telegram after approval: «Reel sizning <repo nomi> repongizga yuklandi» with a link to the reel folder.

## 5. Tests and proof
- pytest: choosing an existing repo; clone instead of init; publish on top of a remote that moved ahead (rebase,
  no force); conflict path keeps the reel and reports; guard still refuses the code repo; his layout detected and
  followed; posted.md line appended in his format; nothing outside the new reel folder + posted.md is changed
  (assert with `git diff --name-only`). Use a local bare copy of his repo, never the real remote.
- Screenshots of the new GitHub settings flow (phone + desktop, light + dark) via the existing screenshot scripts,
  run under `systemd-run --user --scope -p MemoryMax=3G`.
- Update `docs/OWNER_TODO.md` with a short Uzbek section for Javohir: install, connect GitHub, choose
  «Mavjud repomni ulash» → the-suvyektiv-media, connect his Buffer and Telegram.
- Full test suite green; commit and push to origin (code repo) when done.
