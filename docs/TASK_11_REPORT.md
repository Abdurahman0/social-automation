# Task 11 — Windows: hamma matn UTF-8 da (cp949 xatosi) — hisobot

## Egasi uchun qisqacha (o'zbekcha)

**Nima bo'lgan edi.** Koreyscha Windows'da (tizim kodlashi cp949) Telegram'ga shunday xabar keldi:
«Mavzu qidirish» to'xtatildi — Sabab: `'cp949' codec can't encode character '\xe7'`. Reel 5 marta urinib,
«To'xtab qoldi» holatida qoldi.

**Sababi.** Windows'da Python kodlash aytilmagan har bir matn o'qish/yozishda kompyuter tilining kod sahifasini
ishlatadi (Koreyscha Windows'da cp949). Bot Claude'ga savolni (promptni) shunday yuborardi
(`claude_client.py`, `subprocess.run(..., text=True)` kodlashsiz). Promptda `ç` kabi harf bo'lsa, uni cp949 ga
o'girib bo'lmaydi, shuning uchun Claude'ga qilingan har bir murojaat yiqilardi. Xuddi shu xato yana 40 ta joyda bor edi:
git, ffmpeg, Remotion, cloudflared chaqiruvlari va fayllarni o'qish/yozishda.

**Nima qilindi.**
1. Har bir dastur chaqiruvi (git, ffmpeg, Claude, Remotion, cloudflared) endi `encoding="utf-8", errors="replace"`
   bilan ishlaydi: tushunarsiz bayt bo'lsa ham bosqich to'xtamaydi.
2. Har bir matnli fayl o'qish/yozish `encoding="utf-8"` bilan (Instagram/YouTube tokenlari fayli, sayt kaliti,
   reel raqami belgisi, skriptlar).
3. Claude jarayoniga `PYTHONUTF8=1` va `PYTHONIOENCODING=utf-8` beriladi.
4. Dastur kirish nuqtasida (`python -m socialauto ...`) Windows'da UTF-8 rejimi o'chiq bo'lsa, bot o'zini bir marta
   `python -X utf8` bilan qayta ishga tushiradi. Konsol chiqishi ham UTF-8 ga o'tkaziladi, shuning uchun log hech
   qachon `ç`, koreyscha harf, oʻ/gʻ yoki emoji sabab yiqilmaydi.
5. `install.ps1` va fon vazifasi (`scripts/windows_service.ps1`) Python'ni `-X utf8`, `PYTHONUTF8=1`,
   `PYTHONIOENCODING=utf-8` bilan ishga tushiradi.
6. Himoya testi: `tests/test_utf8.py` butun kodni tekshiradi. Kodlash aytilmagan yangi matnli o'qish/yozish yoki
   `text=True` paydo bo'lsa, testlar qizil bo'ladi va xato qaytib kela olmaydi.

**To'xtab qolgan reel.** Hech narsa o'zi qayta yuborilmaydi (qoida). Yangilanishdan keyin Telegram'dagi o'sha
«❌ «Mavzu qidirish» to'xtatildi» xabaridagi **«🔄 Qayta urinish»** tugmasini bosing: tadqiqot o'sha g'oya bilan qayta
ishlaydi (harflar buzilmaydi) va mavzular sizga tasdiqlash uchun keladi. Buni test tekshiradi.

### Windows kompyuterda qanday yangilanadi
- **O'zi:** bot har 6 soatda yangilanishni tekshiradi va o'zi o'rnatadi (faqat fetch + fast-forward), keyin qayta
  ishga tushadi. Hech narsa qilish shart emas. Eski fon vazifasi UTF-8 sozlamasini bilmasa ham, 4-banddagi qayta ishga
  tushirish buni hal qiladi.
- **Darhol:** saytda Sozlamalar → «Yangilanish bor» → **«Yangilash»** tugmasi.
- **Qo'lda (eng to'liq, fon vazifalarini ham yangilaydi):** PowerShell'da:
  ```powershell
  cd $env:USERPROFILE\social-automation
  git pull --ff-only
  powershell -ExecutionPolicy Bypass -File install.ps1
  ```
  So'ng Telegram'da to'xtab qolgan reel xabaridagi «🔄 Qayta urinish» tugmasini bosing.

`.env`, `secrets/`, `data/`, `config.local.toml` va kontent reposiga tegilmaydi.

## Spec checklist

| # | Item | Done |
|---|------|------|
| 1 | Every `subprocess.run/Popen` in text mode → `encoding="utf-8", errors="replace"`: `claude_client.py` (auth status + generate), `updater.py`, `content_repo.py`, `web/repo.py`, `voice.py`, `reel/align.py`, `reel/render.py`, `video/ffmpeg.py` (5 calls), `platforms/tunnel.py`, `scripts/demo_reel.py`. `claude_login.py` was checked: it reads and writes bytes (pty / binary pipes, decoded as UTF-8 with replacement), so it needed no change. Claude child env has `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`. | ✅ |
| 2 | Text `open`/`read_text`/`write_text`: `platforms/instagram.py`, `platforms/youtube.py`, `reel/naming.py`, `web/server.py`, all of `scripts/` (screenshots, demo, theme check). The log `RotatingFileHandler` was already UTF-8. No text-mode csv/tempfile use exists (the lint covers them). | ✅ |
| 3 | `socialauto/utf8.py`: re-exec with `-X utf8` on Windows when `sys.flags.utf8_mode == 0` (loop-guarded) and `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`, called first in `__main__.main()`. `install.ps1` + `windows_service.ps1`: `PYTHONUTF8`, `PYTHONIOENCODING`, UTF-8 console, `-X utf8`. | ✅ |
| 4 | `tests/test_utf8.py`: AST lint over `socialauto/` + `scripts/` (with a self-test that it catches the original line); the real `ClaudeClient` path with a prompt containing `ç`, Korean, oʻ/gʻ and emoji, under a simulated cp949 locale (`locale.getpreferredencoding`, `io.text_encoding`, `PYTHONIOENCODING=cp949`) and a fake `claude` binary that decodes stdin strictly as UTF-8. A control test proves the simulation reproduces the owner's crash with the old call; with the pre-Task-11 `claude_client.py` the test fails. | ✅ |
| 5 | Stuck reel: research fails 5× with the exact cp949 error → «To'xtab qoldi» + «🔄 Qayta urinish»; after the fix the button re-runs research with the idea intact, the reel stops at topic approval (owner step), nothing is posted or queued. | ✅ |
| 6 | Full suite: **266 passed, 1 skipped** (the opt-in test against a local copy of Javohir's real repo, `SA_SUV_BARE`); the PowerShell parser check of the edited `install.ps1` / `windows_service.ps1` passed, run under `systemd-run --user --scope -p MemoryMax=3G`. | ✅ |

## Files
- new: `socialauto/utf8.py`, `tests/test_utf8.py`, `docs/TASK_11_REPORT.md`
- changed: `socialauto/__main__.py`, `socialauto/claude_client.py`, `socialauto/updater.py`, `socialauto/content_repo.py`,
  `socialauto/web/repo.py`, `socialauto/web/server.py`, `socialauto/voice.py`, `socialauto/reel/align.py`,
  `socialauto/reel/render.py`, `socialauto/reel/naming.py`, `socialauto/video/ffmpeg.py`,
  `socialauto/platforms/tunnel.py`, `socialauto/platforms/instagram.py`, `socialauto/platforms/youtube.py`,
  `install.ps1`, `scripts/windows_service.ps1`, `scripts/*.py` (6 helper scripts), `tests/conftest.py`,
  `docs/DECISIONS.md`

## Open owner items
None. The fix reaches the Windows PC through the bot's own update. The stuck reel is restarted by the owner pressing
«🔄 Qayta urinish» (law 3: nothing restarts or posts by itself).
