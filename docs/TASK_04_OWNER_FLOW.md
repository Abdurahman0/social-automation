# Task 04: Rebuild the pipeline around the owner's own reel flow

Owner's request (2026-11-08): "Make sure the project supports my flow FULLY." The flow below is how the owner made
reels by hand. The bot must now do every "Men" (assistant) step automatically and give the owner only the
"Siz" (owner) steps, through Telegram and the website. All laws in `CLAUDE.md` apply (completion, approval first,
dry_run, UI, secrets, free only, memory, lessons). Finish TASK_03 first, then this. Commit in small steps.

The current bot does NOT match this flow (English "facts" niche, AI images, FFmpeg-only montage, Whisper,
direct IG/YT posting, bot-made covers). Change it; keep what already works (Telegram approvals, owner voice,
analytics site, dry-run, lessons store).

## The owner's flow (source of truth)

### 1. Research and topic
- Bot: pull IG statistics from Buffer (views, shares, comments, average watch time) and work out which format works.
- Bot: search the latest Uzbekistan water and wastewater news and world trends. Every number is verified
  against a source.
- Bot: dedupe against the last 30 posts and earlier research files. Topic stays strictly within water / wastewater.
- Bot: write `research/<date>-....md`: 3–5 topics, strongest first, each with sources.
- Owner: picks the topic (Telegram buttons, one per topic + "boshqa mavzular").

### 2. Script
- Bot: 8-part script: hook · lead · body 1 · open loop · body 2 · open loop · body 3 · CTA.
  45–60 s. The answer or the strongest fact in the first 5 s. After every term a plain "ya'ni ..."
  explanation (double tap). Language: Uzbek (make the video language configurable, default `uz`).
- Owner: reads and edits the script (existing Edit button; also accept a pasted full edited script).
- Owner: records and uploads the voice (existing voice flow).

### 3. B-roll and design
- Bot: collect REAL video and photo B-roll (Mixkit, UzA and other free sources with a license that allows
  reuse; Pexels/Pixabay are fine too) — no cartoons, no 3D, no AI images for this channel. Record each clip's
  source and license in the work folder. Work folder: `work/<date>-<topic>/` (the Linux equivalent of
  `C:\MediaBuffer\_work\...`; make the base path configurable, outside any cloud-synced folder).
- Bot: build the composition in **Remotion** (Node is installed): real photo/video + infographics, title at the
  top, subtitles at eye level. No text in the bottom ~20 % or at the right edge (IG UI safe zones). Add a
  safe-zone check to the quality gate.

### 4. Voice and edit
- Bot: split the voice into chunks at pauses, transcribe with **NavaiSTT** (Uzbek STT), and align subtitles and
  scenes to the words (port the role of the owner's `align_voice.py`: words → subtitle timings + scene cuts).
  NavaiSTT and `align_voice.py` are NOT on this machine. Research NavaiSTT; if it is free and runs locally, use
  it. If not, use the best free local Uzbek option (e.g. an Uzbek fine-tuned Whisper / wav2vec2) PLUS forced
  alignment against the approved script (the text is known, so alignment beats free transcription). Record the
  choice in `docs/DECISIONS.md`; if the owner has the original files, ask for them in `docs/OWNER_TODO.md`.
- Bot: clean the voice: highpass 80 Hz, compressor. Music ducks under the voice; overall loudness -14 LUFS.
- Bot: render to `exports/<date>-<topic>_vN.mp4`. Every render gets a new N; never overwrite an old version.
- Bot: run a reel-mistakes checklist before AND after render (create `docs/reel-mistakes-checklist.md` from
  the rules here + lessons store; it grows with every lesson). Extract and check the frames at every section
  boundary (8 parts) — show them in the quality report.

### 5. Approval and posting
- Owner: watches the video, sends fixes (text or voice note → bot re-renders as `_v(N+1)`) or approves.
- Owner: makes the cover. The bot does NOT make covers for this flow: after approval it asks the owner to
  send the cover image in Telegram (remove/disable bot-made thumbnails for this channel).
- Bot: push the reel + cover to the GitHub repo under `reels/<date>-<topic>/` (with the research file, script
  and source list). Video files may be large: use Git LFS if a file is > 50 MB, otherwise plain git. The repo
  link is an owner item (`OWNER_TODO`); until then it is committed locally and shown as "kutilmoqda" on the site.
- Bot: create **Buffer drafts** for Instagram, YouTube and LinkedIn with captions in the owner's style (learn
  the style from the owner's previous Buffer posts; keep a style file). Do NOT schedule or publish.
- Owner: approves and schedules in Buffer.
  Research the current Buffer API. If drafts cannot be created on the owner's plan for free, say so in
  `OWNER_TODO` with the exact gap and keep the existing direct IG/YT publishing as a fallback (off by default).

### 6. After it goes live
- Bot: once the reel is live (detect via Buffer/IG), create a Story draft: the cover image + a link sticker to
  the reel. If the API cannot attach a link sticker, prepare the image and the link and send them to the owner
  in Telegram with one-line instructions.
- Owner: publishes the story.

### Naming rule
Folders and files are always named by the PUBLISH date (`YYYY-MM-DD-topic`). If the publish date changes, the
bot renames everything (work folder, exports, research file, `reels/` folder, Buffer draft titles) to the new
date. Write a test for this.

## Telegram and website
- Telegram shows each owner step as one clear message with buttons (Uzbek): pick topic → edit/approve script
  → send voice → watch video → send cover → "Buffer'da tasdiqlang" → "Storyni joylang".
- Website: the pipeline board shows these exact 6 stages with "Siz" / "Bot" labels, the current version (vN),
  the research file (rendered nicely, sources as names), the B-roll sources, the checklist result and frames.
  UI law applies.

## Done means
- Every bullet above implemented or, if it needs the owner (Buffer access, GitHub repo, NavaiSTT files), a
  precise item in `docs/OWNER_TODO.md` — never faked.
- pytest for: research dedupe (30 posts), 8-part script validator (parts, length, first-5-s rule, "ya'ni"
  rule), safe-zone check, `_vN` versioning, date rename, Buffer draft payload (mocked), story step.
- A full dry-run demo on one water topic in Uzbek (test voice allowed for the demo only): research file,
  script, real B-roll, Remotion render `_v1`, checklist, section frames — saved in `proof/` with phone/tablet/
  desktop screenshots of the site. Update `README.md`, `docs/DECISIONS.md`, `proof/REPORT.md` (Uzbek).
- Fill the table at the end of `proof/REPORT.md`: every flow step → where it is implemented → test/proof.
