# Task 11 — Windows: every text I/O in UTF-8 (cp949 crash)

## Bug (live, owner's Windows PC, Korean locale)
Telegram: «Mavzu qidirish» to'xtatildi — «Yangi tadqiqot».
Sabab: 'cp949' codec can't encode character '\xe7' in position 720: illegal multibyte sequence. 5 retries, reel stuck «To'xtab qoldi».

Root cause: on Windows Python uses the locale code page (cp949 on Korean Windows) for every text-mode
I/O that has no explicit encoding. `socialauto/claude_client.py:156` runs
`subprocess.run(cmd, input=prompt, ..., text=True)` with no encoding → the prompt (contains 'ç' etc.)
cannot be encoded to cp949 → every Claude call with a non-cp949 char fails. Same class of bug exists in many places.

## Do
1. Every `subprocess.run/Popen/check_output` with `text=True`/`universal_newlines` → add `encoding="utf-8", errors="replace"`
   (claude_client.py 120+156, claude_login.py, updater.py, content_repo.py, web/repo.py, voice.py, reel/align.py,
   reel/render.py, video/ffmpeg.py, platforms/tunnel.py — grep for all; don't trust this list).
   For the Claude child also set env `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8` in child_env.
2. Every `open()` in text mode, `Path.read_text()`, `Path.write_text()`, `json.load(open())`, logging FileHandler,
   csv, tempfile in text mode → explicit `encoding="utf-8"`. Grep the whole package + scripts/.
3. Belt and braces: at program entry (`socialauto/__main__.py` / cli entry) and in install.ps1 / Windows launchers,
   run with UTF-8 mode (`PYTHONUTF8=1`, or re-exec with `-X utf8` if `sys.flags.utf8_mode == 0` on Windows).
   Also `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` so console logging never crashes.
4. Regression test (pytest): a lint-style test that AST-scans `socialauto/` and fails on any text-mode
   open/read_text/write_text/subprocess text=True without an `encoding=` kwarg. Plus a test that runs
   the ClaudeClient subprocess path with a prompt containing 'ç', Korean, Uzbek oʻ/gʻ, emoji, under
   `PYTHONIOENCODING=cp949`/locale simulation (monkeypatch `locale.getpreferredencoding` → 'cp949'),
   using a fake claude binary — must pass.
5. Stuck reels: reels left «To'xtab qoldi» because of this error must be retryable by the existing button; verify
   the retry path works after the fix (test). Do not auto-post anything (owner law).
6. All tests green. Write docs/TASK_11_REPORT.md (Uzbek summary: cause, fix, files, how owner updates on Windows —
   the bot's own updater/`git pull` + restart). Commit mentioning Task 11 and push to origin main (never force).
