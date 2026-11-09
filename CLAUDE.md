# Social Automation: project laws

A local service with ONE Telegram bot that makes short reels with the owner's voice, gets the owner's approval at every
owner step, and puts each approved reel into Buffer's QUEUE (Instagram, YouTube, LinkedIn); Buffer posts it at its own
next free posting-schedule time. A website shows live statistics and analytics and the pipeline.

## Owner laws (never break)
1. **Completion law:** finish every item fully. No stubs, TODOs, placeholders, fake data in the UI, or skipped
   parts. Check the spec item by item before calling it done. Only a real external gap may stay open (for example
   an account the owner still has to connect). It goes into `docs/OWNER_TODO.md` and is never faked.
2. **Owner time is scarce.** Decide sensible defaults yourself, finish end to end, ask only owner-only things,
   batched, in `docs/OWNER_TODO.md`.
3. **Approval first:** nothing moves to the next owner step without the owner pressing Approve in Telegram.
4. **Safe by default:** `dry_run = true` on a new install until the owner connects Buffer and switches it off
   (`python -m socialauto dry-run off`). In dry-run nothing is sent to Buffer: it is only recorded locally
   (`data/dryrun_posts.json`).
5. **Telegram is quiet:** the owner gets only his own steps (approvals, voice, cover, "Buffer navbatiga qo'shildi",
   story), and alerts they must act on
   (auth expired, limit reached with the reopen time in Tashkent time). Errors go to logs.
6. **UI law (website + Telegram):** never show raw backend JSON, error codes, UUIDs or internal ids. Show names,
   titles, thumbnails, numbers. Beautiful, creative design. No scroll/layout bugs. Good on phone, tablet and
   desktop. Handmade date picker / select / checkbox controls (no raw browser ones).
7. **Secrets:** tokens and OAuth files live in `.env` and `secrets/` (gitignored, chmod 600). Never print,
   log, commit or send them.
8. **Free only:** no paid APIs or services without the owner's OK. Claude runs through the Claude Code
   subscription login (CLI), never an API key.
9. **Memory (7.4 GB machine):** wrap every heavy command (video render, browser, npm build, tests that render) in
   `systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue -- <cmd>`.
   One dev server at a time. Run `free -h` first.
10. **Do not touch** `~/youtube-automation` (live bot), `~/telegram-ai-agent`, `~/.claude-youtube`. You may
    read `~/youtube-automation` and copy code from it into this repo.
11. **Lessons:** every failure and its fix is recorded (lessons store) and fed into later generation prompts so
    the same mistake is never repeated.
12. **Git:** commit in small steps with clear messages. Remote: `git@github.com:Abdurahman0/social-automation.git`.
    Push to main, never force-push. Only the owner writes to this code repo; the app only fetches updates from it. `proof/`, `.env`, `secrets/`, `data/`, `logs/`, `work/`, `models/` never
    go to GitHub; the full pre-publication history stays only in the local branch `local-history`.
13. Owner talks in Uzbek or English; Telegram texts to the owner are in Uzbek unless config says otherwise.
    Video content is in Uzbek by default (configurable, `[reel] language`; owner, Task 04).
14. **Owner's voice:** the narration is always the owner's own recording uploaded to the Telegram bot. Never
    TTS for real videos. Details: `docs/TASK_02_OWNER_VOICE.md`.
15. **Approved reels go into Buffer's queue; the bot never posts directly** (owner, 2026-11-08; changed by the owner
    2026-11-09). After the owner approves the video (and sends the cover) in Telegram, the reel is added to Buffer's
    queue for Instagram, YouTube and LinkedIn (`mode: addToQueue`, `schedulingType: automatic`) and Buffer posts it at
    each channel's next free posting-schedule time. The bot never picks a time (no `dueAt`, share-now or custom
    schedule) and never uploads or publishes on a platform itself: platform clients are read-only (statistics), guard
    test `tests/test_guards.py`. The story stays a Buffer DRAFT (`saveToDraft: true`) that the owner publishes himself.
16. **The bot NEVER makes a cover / thumbnail** (owner, 2026-11-08). After the owner approves the video, the bot asks
    for the owner's cover in Telegram and waits; the cover is used as is (only a format conversion if Buffer needs
    it, and the owner is told). No generated, fallback or burned-in cover of any kind.
17. **Every user, own accounts; the code repo is read-only** (owner, 2026-11-08, Task 07). Each install uses its
    user's own Telegram bot, Buffer, GitHub, Claude, Instagram and YouTube logins, all entered on the website and
    stored only on that computer. Reels go to the user's OWN content repo (`data/content-repo` →
    `<login>/social-automation-content`, private). The app never commits or pushes to the code repo: a hard guard
    (`socialauto/content_repo.py`, test `tests/test_content_repo.py`) refuses it on every computer. Updates are
    fetch + fast-forward only (`socialauto/updater.py`). This computer's own settings go to `config.local.toml`.
