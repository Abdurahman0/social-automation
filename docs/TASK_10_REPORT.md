# Task 10 — har bir xato Telegram'ga keladi; «/new <g'oya>» shu g'oya bo'yicha qidiradi (hisobot)

## Egasi uchun qisqacha (o'zbekcha)

**Nima bo'lgan edi.** Siz /new yozdingiz, «🔎 Tadqiqot boshlandi…» keldi, keyin hech narsa kelmadi. Sabablar
(endi hammasi yopildi):
1. Tadqiqot xato bersa, bot uni 2, 4, 8, 16, 32 daqiqadan keyin jim qayta urinib, oxirida **jimgina** to'xtatardi.
2. Claude topgan mavzular filtrdan o'tmasa (suv yo'nalishiga mos emas / manbasi yo'q / «avval bo'lgan»), bu ham
   oddiy xato sifatida jim yo'qolardi. Bundan tashqari sizning g'oyangizning **o'zi** «avval bo'lgan mavzular»
   ro'yxatiga tushib qolardi va shu g'oya haqidagi mavzularni o'chirib yuborardi; g'oya haqidagi mavzular bir-biriga
   «o'xshash» deb ham tashlanardi.
3. /new yonidagi so'z faqat «maslahat» edi — Claude uni asosiy shart sifatida olmasdi.
4. Bot pauzada bo'lsa ham «Tadqiqot boshlandi» deyardi; to'xtab qolgan reel /new ni abadiy to'sib qo'yishi mumkin edi.

**Endi Telegram'da ko'radigan xabarlaringiz** (haqiqiy kod chiqargan matnlar, `proof/task10/example_messages.txt`):

```
⚠️ «Mavzu qidirish» bosqichida xato
🎬 «Toshkentda ichimlik suvi»
Sabab: Claude javobi juda uzoq cho'zildi (vaqt tugadi) — internet sekin yoki xizmat band.
🔁 2 daqiqadan keyin o'zim qayta urinaman.
```
```
🔎 Mavzu topilmadi
🎬 «Futbol chempionati»
Sabab: topilgan 6 ta mavzudan 6 tasi suv / oqova suv yo'nalishiga mos kelmadi.
Reel saytda «To'xtab qoldi» holatida turibdi. Qayta urinish uchun tugmani bosing.
Yoki boshqa g'oya bilan yozing: /new <g'oya>.
[🔄 Qayta urinish] [🔎 Boshqa mavzu]
```
```
❌ «Video yig'ish» to'xtatildi
🎬 «Suvning 40 foizi yo'qoladi»
Sabab: ffmpeg o'rnatilmagan (video va ovoz bilan ishlash uchun kerak) — o'rnatuvchini qayta ishga tushiring.
3 marta urinib ko'rdim.
Reel saytda «To'xtab qoldi» holatida turibdi. Qayta urinish uchun tugmani bosing.
[🔄 Qayta urinish]
```
```
📡 Internet yo'q — bot ishlarni to'xtatib turibdi. Internet qaytishi bilan o'zi davom etadi (alohida xabar beraman).
✅ Internet qayta ulandi — ishlar davom etyapti.
```

**/new endi qanday ishlaydi:**
- `/new Toshkentda ichimlik suvi` → «🔎 «Toshkentda ichimlik suvi» bo'yicha mavzular qidirilyapti… (odatda 3–10
  daqiqa)». Claude internetdan aynan shu g'oya haqida 3–5 ta burchak topadi (har birida «nega hozir», birinchi 5
  soniya, manbalar), suv yo'nalishida va brend qoidalaringiz bilan. Ro'yxat ««…» bo'yicha mavzular tayyor» sarlavhasi
  va bitta izoh qatori bilan keladi. «🔎 Boshqa mavzular» ham shu g'oya bo'yicha qidiradi.
- G'oya suvdan tashqarida bo'lsa (masalan, futbol), Claude eng yaqin suv mavzularini topib, buni izohda aytadi.
- Faqat `/new` → «💡 Qaysi g'oya bo'yicha?» — keyingi xabaringiz g'oya bo'ladi; `/skip` yoki «🎲 Bot o'zi
  tanlasin» — bot mavzuni o'zi tanlaydi (avvalgidek).
- Pauzada: «⏸ Avtomatik ish to'xtatilgan — /resume bosing…».
- `/status` endi oxirgi xatoni (bosqich, Toshkent vaqti, sabab) va qayta urinishni kutayotgan ishlar sonini ko'rsatadi.

**Spam yo'q:** bitta ish uchun bitta xato bir marta (boshqa xato bo'lsa — yana bir marta); internet yo'qligi —
bitta xabar va qaytganda bitta xabar; statistika / avtomatik yangilanish / ishga tushish tekshiruvi xatosi — bir
marta, tuzalib yana buzilgandagina qayta.

**Sizdan hech narsa talab qilinmaydi.** Boshqa kompyuteringiz yangilanishni o'zi oladi (quyida).

## Bajarildi — talab bo'yicha

| Talab | Qayerda | Test |
|---|---|---|
| §1 Birinchi xato: bosqich nomi (o'zbekcha), reel/mavzu, oddiy sabab, «N daqiqadan keyin o'zim qayta urinaman» | `errors.py` (`STEP_UZ`, `explain`, `ErrorReporter.job_failed`), `workflow._failed` | `test_first_failure_is_told_once_with_the_retry_time` |
| Sabablar xaritasi: internet/timeout, Claude WebSearch, Claude CLI yo'q, ffmpeg/model yo'q, B-roll kaliti, disk to'la, GitHub rad etdi, mavzular filtrlangan; boshqasi — 1 qator, sirlar o'chirilgan | `errors.explain`, `redact`, `short` | `test_explain_maps_common_causes`, `test_secrets_never_reach_the_message` |
| Bir xil xato — spam yo'q (ish × xato kodi bo'yicha bir marta) | `ErrorReporter.job_failed` (`joberr:<id>`) | o'sha test (3 urinish → 2 xabar) |
| To'xtatish: «❌ … to'xtatildi» + sabab + «🔄 Qayta urinish» (+ tadqiqotda «🔎 Boshqa mavzu»); reel xatosi bilan ko'rinib turadi | `job_gave_up`, `Workflow.retry_failed`, tugma `er:r:/er:o:` | `test_give_up_message_and_retry_button_re_enqueues`, `test_render_give_up_keeps_the_reel_visible_with_its_error`, `test_zero_topics_is_explained_and_other_topic_button_works` |
| Nol mavzu — sababi bilan xabar (mos emas / avval bo'lgan / manbasi yo'q), qayta-qayta urinmaydi | `research.filter_topics`, `why_empty`, `NoTopicsError` | `test_zero_topics_…`, `test_topics_without_sources_are_explained` |
| Telegram handler xatosi → egasiga qisqa o'zbekcha javob | `TelegramBot.on_error` / `report_handler_error` | `test_telegram_handler_error_answers_in_uzbek` |
| Scheduler/runner sikli qulashi | `Scheduler._jobs`, `TelegramBot._guarded` → `reporter.problem` | `test_scheduler_loop_crash_reaches_the_owner` |
| Avtomatik yangilanish xatolari | `Scheduler.check_update` / `_updates` | `test_auto_update_installs_and_reports_failures_once` |
| Ishga tushishdagi «Sozlash» tekshiruvlari (ffmpeg, nutq modeli, Remotion, dry_run o'chiq + Buffer kaliti yo'q) | `runner.startup_checks` | `test_startup_checks_alert_once` |
| Statistika yangilanmasa / Buffer holati / story qoralamasi xatosi | `Scheduler._analytics`, `Workflow._live_check_problem`, `check_live` | `test_periodic_problem_is_told_once_until_fixed` |
| Pauzada /new → «⏸ … /resume bosing» | `TelegramBot.new_command` / `new_reply` | `test_paused_new_says_so` |
| Watchdog: limitdan uzoq ish xabar qilinadi va qayta navbatga qo'yiladi; egasiz «running» qator ham | `Scheduler.run_one`, `check_orphans`, `Workflow.job_timed_out`, `JobQueue` urinish-tekshiruvi | `test_watchdog_reports_and_requeues_a_stuck_job`, `test_orphan_running_row_is_requeued` |
| RESEARCHING/DRAFTING jonli ishsiz /new ni to'smaydi; «allaqachon ketyapti» faqat ish haqiqatan tirik bo'lsa | `Workflow.start_research` | `test_stuck_research_does_not_block_new`, `test_research_waiting_to_retry_gives_way_to_a_new_idea`, `test_stuck_drafting_is_resumed_and_new_starts` |
| `/status`: oxirgi xato (bosqich, Toshkent vaqti, sabab) + qayta urinish kutayotganlar | `status_text`, `ErrorReporter.status_lines` | `test_status_shows_the_last_error_and_retry_count` |
| Outbox orqali (restartdan keyin ham yo'qolmaydi); internet: bitta «yo'q», bitta «qayta ulandi»; onlayn paytdagi uzilish «internet yo'q» emas | `Outbox` kind `error`, `ErrorReporter._offline/back_online`, `Scheduler._network` | `test_offline_is_one_message_then_one_back_online`, `test_a_network_blip_while_online_is_not_internet_down`, `test_error_message_is_delivered_with_buttons` |
| §2 `/new <g'oya>` — g'oya asosiy shart (prompt), filtrlar g'oya mavzularini tashlamaydi | `research.prompt(idea=…)`, `filter_topics(idea=…)`, `Workflow.recent_titles`, `job_research` | `test_new_with_an_idea_researches_that_idea` |
| `/new` yolg'iz — eski xatti-harakat (bot tanlaydi) `/skip` yoki tugma orqali; keyingi xabar g'oya sifatida | `new_command`, `cmd_skip`, `AWAIT_IDEA`, `nw:auto` | `test_new_alone_asks_then_skip_lets_the_bot_pick`, `test_new_then_the_idea_as_the_next_message` |
| Javob g'oyani nomlaydi; ro'yxat g'oya va izoh bilan | `new_started_text`, `topic_message(idea, idea_note)` | yuqoridagi testlar |
| Sayt: to'xtagan reel «Jarayon»da sababi bilan, reel sahifasida «⚠️ To'xtab qoldi» va «💡 Sizning g'oyangiz» | `web/server.py` (`failed_stage`, `error_text`), `app.js`, `app.css` | `test_stopped_reel_is_visible_on_the_website_with_its_reason` |
| Avtomatik tsikl yo'q: to'xtagan tadqiqot 24 soat ichida o'zi qayta boshlanmaydi | `Workflow.ensure_pipeline` | `test_a_stopped_research_is_not_restarted_automatically_in_a_loop` |
| CLI: `python -m socialauto new "<g'oya>" --run` | `__main__.cmd_new` | `test_cli_new_runs_the_research` + haqiqiy ishga tushirish (quyida) |
| README / HELP | `README.md` («Telegram commands», «Update»), `telegram_bot.HELP` | — |
| DB migratsiyasi avtomatik | `db._add_idea` (reels.idea, reels.idea_note) | `test_db_migration_adds_the_idea_columns` |

## Haqiqiy tekshiruv (shu kompyuter, Claude CLI bor, dry-run, Telegram tokeni yo'q)

### 1. `python -m socialauto new "Toshkentda ichimlik suvi" --run`

To'liq chiqish: `proof/task10/e2e_new_idea.txt`; Telegram'ga ketadigan aynan matn: `proof/task10/e2e_topic_message.html.txt`.
Claude 130 soniyada javob berdi, 4 ta mavzuning hammasi filtrlardan o'tdi va hammasi g'oya haqida:

1. **Toshkentda ichimlik suvi narxi ikki baravar oshadimi?** — nega hozir: 30-oktabr 2026 «O'zsuvta'minot» 3 100
   so'mlik taklifni e'lon qildi; birinchi 5 s: «bir kub metr suv qariyb 1 600 so'm… endi 3 100 so'm taklif qilindi»;
   manbalar: UzDaily.uz, Spot.uz.
2. **Poytaxtda 98,6% suv bor, lekin bu mahallada faqat 20%** — Yashnobod tumani Kengashi qarori (28-oktabr 2026);
   manbalar: UzA, Anhor.uz.
3. **670 ming xonadonga bepul aqlli suv hisoblagichi: nima o'zgaradi?** — SUEZ bilan loyiha, 2031-yilgacha;
   manbalar: Tashkent Times, UzA.
4. **Toshkent ichimlik suvi bir yilda: 672 mln kub va 25 ming nosozlik** — manbalar: UzA, Kun.uz, Anhor.uz.

Izoh (idea_note): «Barcha mavzular to'g'ridan-to'g'ri Toshkent ichimlik suvi haqida: narxi, sarfi, suvi yo'q
mahallalar, aqlli hisoblagichlar va tizimning hajmi.»
Outbox: `topic_choice` (mavzular ro'yxati + tugmalar), xato xabari yo'q.

### 2. G'oya suvdan tashqarida: `python -m socialauto new "Futbol chempionati" --run`

To'liq chiqish: `proof/task10/e2e_new_offniche_idea.txt`. Claude 97 soniyada 4 ta eng yaqin suv burchagini berdi va
buni izohda ochiq aytdi: «Futbol chempionatining o'zi suv mavzusi emas, shuning uchun bu yerda unga eng yaqin suv
burchaklari berilgan: mezbon shaharlardagi suv tanqisligi, maydonni sug'orishga ketadigan suv, oqova suvni qayta
ishlatish va o'yinchilar uchun suv tanaffusi.»

1. Jahon chempionati va Mexiko: 4 xonadondan 1 tasiga suv har kuni kelmaydi (IPS News)
2. Qatar chempionati: bitta futbol maydoniga kuniga 50 ming litr suv (Physics World, Euronews)
3. Jahon chempionatida har o'yinda 2 marta suv tanaffusi: nega? (FIFA)
4. Yomg'ir suvini yig'adigan stadion: 680 ming gallonlik sardoba (Mercedes-Benz Stadium rasmiy sayti)

Outbox: `topic_choice`. Agar Claude faqat suvdan tashqari mavzular qaytarsa, «🔎 Mavzu topilmadi … N tasi suv /
oqova suv yo'nalishiga mos kelmadi» xabari keladi (test: `test_zero_topics_is_explained_and_other_topic_button_works`).

Ikkala sinov reeli shu kompyuterning bazasida «Rad etildi» deb yopildi va ularning Telegram xabarlari «yuborilmaydi»
deb belgilandi — bu kompyuterda keyin Telegram ulansa, eski sinov ro'yxati kelib qolmaydi.

## Testlar

`pytest`: **253 passed, 1 skipped** (o'tkazib yuborilgani: Javohirning haqiqiy reposi nusxasi bilan ishlaydigan test, faqat `SA_SUV_BARE` berilganda ishlaydi) (shu jumladan yangi `tests/test_errors.py` — 48 ta test). Hammasi
`systemd-run --user --scope -p MemoryMax=3G …` ichida ishga tushirildi.

## Yangilanish boshqa kompyuterga qanday yetadi

- Bot endi o'zi yangilanadi: har `update_check_hours` (6 soat; ishga tushgandan 2 daqiqa keyin birinchi tekshiruv)
  `git fetch` + faqat fast-forward (`Updater`), keyin `data/restart_request` → bot qayta ishga tushadi; sayt ham endi
  shu faylni kuzatadi va qayta ishga tushadi. `.env`, `secrets/`, `data/`, `config.local.toml` ga tegilmaydi.
- Bu versiyaning o'zi u kompyuterga hali eski kod orqali keladi: saytdagi «Sozlamalar» → «Yangilanish bor» tugmasi
  (yoki `git pull --ff-only`). Shundan keyingi hamma yangilanishlar avtomatik.
- Bazadagi o'zgarish (`reels.idea`, `reels.idea_note`) — migratsiya, bot ishga tushganda o'zi bajariladi.
- O'chirish kerak bo'lsa: `config.local.toml` → `[github] auto_update = false`.

## Qarorlar

`docs/DECISIONS.md` → «Task 10». Asosiylari: nol mavzu darhol to'xtatiladi (qayta urinish bir xil natija beradi,
qaror sizda); qotgan ishni xavfsiz «o'ldirib» bo'lmaydi, shuning uchun u tashlab qo'yiladi, ish qayta navbatga
qo'yiladi va u tirik ekan shu turdagi ikkinchi ish boshlanmaydi (xotira); onlayn paytdagi bir martalik uzilish
«Internet yo'q» deb hisoblanmaydi.
