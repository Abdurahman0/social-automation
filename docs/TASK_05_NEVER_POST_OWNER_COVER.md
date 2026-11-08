# Task 05: The bot never posts, the bot never makes covers (owner law, 2026-11-08)

Owner, 2026-11-08: "I told you how to create the thumbnail! And the bot should never post anything himself!"
This is a permanent LAW. Add it to `CLAUDE.md` (laws section) and `docs/DECISIONS.md`. Finish the running TASK_04
demo first, then do this. Commit in small steps. dry_run stays on.

## Law 1: the bot NEVER publishes or schedules anything, on any platform, in any mode
- The owner's flow: the bot only creates **Buffer drafts** (IG, YouTube, LinkedIn) and a **story draft**; the owner
  approves + schedules in Buffer and publishes the story himself. Nothing else ever leaves the machine as a post.
- REMOVE (not just disable) the direct-posting path: `publish_direct` setting (config.py + config.toml), the
  "🚀 Hozir joylash" / "Vaqtida joylash" buttons and `post_now` / slot-booking actions in `telegram_bot.py` and
  `workflow.py`, the upload/publish code in `socialauto/publishing/youtube.py`, `instagram.py`, `publisher.py`
  (keep only READ-ONLY analytics calls the analytics collector needs, and the read-only Buffer status check that
  detects when the owner's post went live). Drop the old "facts" flow's posting stage; if that flow can't work
  without posting, remove the flow and keep `owner_reel` as the only flow.
- Buffer client: keep `saveToDraft: true` hard-coded; make it impossible to send a non-draft create (no parameter can
  turn it off). Never call any Buffer mutation that schedules, shares now, or publishes. `editPost` only on drafts.
- Guard test: a test that greps the package and fails if any publish/upload/schedule endpoint or method appears
  (YouTube `videos.insert`, IG `media_publish`, Buffer share/schedule mutations, `post_now`, `publish_direct`), and a
  test that every Buffer create call carries `saveToDraft: true`.
- Telegram texts, website (pipeline board, reel page, OWNER_TODO, README) must say "Buffer'da qoralama tayyor —
  tasdiqlab rejalashtirish sizda", never "joylandi / joylanadi / hozir joylash". Remove the "turn off dry-run to go
  live / posting" wording; dry-run now only means "no Buffer drafts are created for real".
- OAuth scopes: request only read-only scopes for YouTube/IG analytics (no upload scope).

## Law 2: the bot NEVER makes a cover / thumbnail; the owner makes it
- Flow step 5: "Siz: cover tayyorlaysiz. Men cover qo'shmayman." After the owner approves the video, the bot asks
  for the cover in Telegram and waits. The owner's image is used AS IS (no crop, no text, no overlay, no resizing
  that changes it; only a format conversion if Buffer requires it, and say so).
- REMOVE `socialauto/video/thumbnails.py` and every call to it (render, demo, quality check, screenshots), the
  `cover_youtube` / `cover_instagram` bot-made fields in the renders table usage, and any AI/PIL cover generation.
  No fallback cover of any kind. If the owner hasn't sent a cover, the reel stays at "Muqova kutilmoqda".
- Remotion/ffmpeg must not burn a cover frame into the video either.
- Story draft uses the owner's cover only.
- Proof images/screenshots must not show a bot-made cover anywhere (regenerate `proof/` without them; delete the old
  bot-made cover files from `proof/`).

## Proof (report in Uzbek, `proof/TASK_05_REPORT.md`)
- `pytest` green, including the two guard tests.
- `grep` output showing no publish/upload/schedule code and no thumbnail generator left.
- One dry-run reel end to end: … → approve video → bot asks for cover → owner cover (test image) → Buffer drafts
  (dry-run log shows `saveToDraft: true`, no scheduled/published entry) → story draft with the owner's cover.
- Telegram screenshot of the step after video approval (asks for the cover, no "joylash" button) and the
  reel page on the website (phone + desktop).
