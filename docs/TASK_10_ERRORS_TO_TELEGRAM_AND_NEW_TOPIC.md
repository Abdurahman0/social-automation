# TASK 10 — Every error reaches Telegram; «/new <idea>» researches topics around that idea

Owner (2026-11-11), using the bot on his OTHER computer (Claude and YouTube connected there): "If any error occurs
in the bot it must come to the socials bot! And when I click /new and write something next to it, it should search
for the themes with this idea." He typed /new, got «🔎 Tadqiqot boshlandi…», then nothing ever came.

All laws in CLAUDE.md apply (secrets, OOM limits: wrap heavy commands in
`systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue --`, never post, owner's
cover law, plain Uzbek for the owner, no raw JSON/ids/stack traces in Telegram). Finish EVERYTHING; decide defaults
yourself; no questions. No partial work, stubs or TODOs.

## 1. No silent failures — every error goes to Telegram (Uzbek, plain words)
Today `workflow.run_job` retries generic exceptions 2,4,8,16,32 min and then `_give_up` ends the job "quietly";
only Claude auth / usage limit / Buffer auth reach the owner. Change it:
- **First failure** of any job (research, script, voice, render, revise, buffer, content repo push, story, stats…):
  send one short Telegram message: which step (Uzbek name: «Mavzu qidirish», «Ssenariy», «Ovoz», «Video yig'ish»…),
  for which reel/topic, a plain-Uzbek reason (map common causes: no internet / timeout, Claude WebSearch failure,
  Claude CLI missing or error, ffmpeg/model missing, Pexels/Pixabay key missing, disk full, GitHub push rejected,
  all research results filtered out as off-niche/no source…; otherwise a 1-line shortened error text, secrets
  redacted), and «N daqiqadan keyin o'zim qayta urinaman». Same error on later retries: no spam (edit/skip; at most
  one message per job per distinct error).
- **Give-up**: always a message: «❌ … to'xtatildi» + reason + buttons «🔄 Qayta urinish» (re-enqueue the same
  job) and, for research, «🔎 Boshqa mavzu» ; the reel stays visible with its error.
- **Research that returns zero usable topics** is an error the owner sees (say why: e.g. «topilgan 6 ta mavzu suv
  yo'nalishiga mos kelmadi» / «manbasi yo'q»), never silently dropped.
- **Bot-level errors**: telegram handler exceptions (python-telegram-bot error handler → short Uzbek reply to the
  owner), scheduler/runner loop crashes, updater (auto-update) failures, web «Sozlash» checks that fail at
  startup (missing ffmpeg, missing keys needed for the next step). A paused bot: /new while paused must say
  «⏸ Avtomatik ish to'xtatilgan — /resume bosing», not «Tadqiqot boshlandi».
- **Stuck job watchdog**: a job running longer than its timeout (research > 20 min, render > 60 min…) is reported
  and retried; a reel stuck in RESEARCHING/DRAFTING with no live job must not block /new forever («allaqachon
  ketyapti» only when a research job is really alive; otherwise clean it up and start).
- `/status` shows the last error (step, time in Tashkent, Uzbek reason) and the number of jobs waiting to retry.
- Use the existing outbox/`_owner_alert` path so messages survive restarts; rate-limit sensibly (no flood if the
  network is down: one «internet yo'q» message, then one «qayta ulandi»).

## 2. «/new <idea>» = research around THAT idea
- `/new Toshkentda ichimlik suvi` (and the «Yangi g'oya» flow / plain text after a /new prompt) must send the idea
  to research as the main constraint: Claude searches the web for 3–5 topic angles **about that idea** (each with
  angle, «nega hozir», first-5-seconds hook, sources), still in the water niche and the brand rules. Check the
  research prompt actually uses `topic` strongly (today it may be only a hint) and that the niche/novelty filters
  do not throw away every idea-related result (if the idea is outside the niche, still give the closest
  water-related angles and say so).
- `/new` alone keeps today's behaviour (bot picks topics itself).
- The reply names the idea: «🔎 «Toshkentda ichimlik suvi» bo'yicha mavzular qidirilyapti… (odatda 3–10 daqiqa)»,
  then the topic list with buttons; if it fails → §1 message.
- Also accept `/new` then the idea as the next message (bot asks «Qaysi g'oya bo'yicha? Yozing yoki /skip»).

## 3. Tests and proof
- pytest for: first-failure message, no duplicate spam, give-up message with retry button that re-enqueues,
  zero-topics message, paused /new reply, stuck RESEARCHING cleanup, Telegram error handler, `/new <idea>` passes
  the idea into the research prompt and results are about it, `/new` alone unchanged. Full suite green.
- A real end-to-end check if this machine can (Claude CLI present): run research with an idea through
  `python -m socialauto new "<idea>"` in dry mode and show the topics it produced in the report (no Telegram token
  here: assert the outbox messages instead).
- Report: `docs/TASK_10_REPORT.md` (Uzbek summary for the owner at top: what messages he will now see, with 3–4
  example texts). Update README/HELP text for /new.
- Commit (messages mention Task 10) and push to origin main (never force). The other computer auto-updates from
  GitHub — make sure the update path picks this up (DB migration if any must be automatic).
