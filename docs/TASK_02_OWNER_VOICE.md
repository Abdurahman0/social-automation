# Task 02: the owner records the voice (no TTS narration)

Owner's decision (2026-11-08): **the owner records the narration himself and uploads it to the Telegram bot.**
This overrides every "Kokoro narration" part of Task 01. Kokoro is NOT used for the voice of real videos.

## New flow
1. Claude writes the script → **Approval 1** (transcript + "What this video is about") exactly as in Task 01.
2. On **Approve**, the bot replies (Uzbek): the transcript to read, target length, and short recording tips
   (quiet room, phone close, read naturally). Status of the video becomes **"Ovoz kutilmoqda"** (waiting for voice).
3. The owner sends the voice to the bot. Accept: Telegram **voice message**, **audio file** (mp3/m4a/wav/ogg/opus/
   aac) and audio sent **as a document**; also a **video note / video** (take its audio track). Respect the Bot API
   20 MB download limit; if bigger, tell the owner kindly (send as voice message or compress).
4. The bot processes the voice (all free, local):
   - FFmpeg → wav; trim leading/trailing silence; light noise reduction (`afftdn`/`highpass`); loudness normalize
     to about -14 LUFS for both platforms; keep it natural (no robot effects).
   - Transcribe locally with Whisper (faster-whisper, small/base on CPU, memory-capped) with **word timestamps**.
     Captions are built from what the owner **actually said**, synced to his voice.
   - Compare with the approved script. Small differences are fine (use the spoken words). If a big part is missing
     or the duration is over the limit, send one short Uzbek message with buttons: **"Shu holicha davom et"** /
     **"Qayta yozib yuboraman"**.
   - Video length follows the voice length (visuals are timed to the real word timestamps).
5. Render video + thumbnails → quality gate (add: voice clipping/too quiet check) → **Approval 2** → post to
   YouTube + Instagram, as in Task 01.

## Rules
- A video is never rendered or posted without the owner's voice. If no voice arrives, send **one** reminder
  about 3 hours before its slot; if still none at slot time, the video quietly moves to the next free slot
  (no other alerts: Telegram-is-quiet law).
- Re-recording: the owner may send a new voice any time before Approval 2 is approved; the newest voice wins
  and the video is re-rendered.
- If the owner sends a voice when no video is waiting for one, the bot asks with buttons:
  "<video title> uchun" (one button per waiting video, newest first) or **"Shu ovozdan yangi video yasa"**
  (transcribe it → Claude writes title/summary/hashtags/visual plan from the spoken text → Approval 1 shows that
  transcript → then the normal flow without asking for voice again).
- Keep the owner's raw voice files in `data/voices/` (gitignored). Never commit them.
- `/queue` and `/status` and the dashboard pipeline view show the new "Ovoz kutilmoqda" stage.
- Lessons store: record voice problems (too quiet, noise, cut words) and include short tips in the next
  recording request.

## Tests and proof (add to Task 01 "Done means")
- pytest: voice/audio/document/video-note intake, wrong file type, over 20 MB, newest voice wins,
  unsolicited voice buttons, missing-voice reminder + slot move, Whisper captions sync (use a short test clip),
  script-vs-speech mismatch buttons.
- The dry-run demo uses a short **test** recording made only for the demo/tests (a Kokoro clip is OK ONLY as a
  test fixture, clearly named `tests/fixtures/sample_voice_*.wav`). Show in `proof/` the "please record" message,
  the voice being accepted, and the final video with captions synced to the voice.
- Update README, `docs/DECISIONS.md`, `docs/OWNER_TODO.md` (how to record and send a good voice, in Uzbek),
  and `proof/REPORT.md`.
