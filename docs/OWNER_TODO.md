# Egasi qiladigan ishlar (faqat siz qila oladigan qadamlar)

Qolgan hamma narsa tayyor va sinov rejimida (dry-run) ishlab turibdi. Har bir qadam — "shuni bosing / shuni joylang".
Terminal buyruqlari loyiha papkasida (`social-automation`) yoziladi.

**Muhim qonunlar (siz belgilagansiz):** Telegram'da tasdiqlagan reelingiz **Buffer navbatiga** tushadi va Buffer uni
o'z jadvali bo'yicha joylaydi (bot vaqtni o'zi tanlamaydi; story Buffer'da qoralama bo'lib qoladi). Bot **muqova qilmaydi** — muqovani siz
tayyorlaysiz, bot uni so'raydi va o'zgartirmasdan ishlatadi.

---

## 1. Telegram bot tokeni va ID — saytdagi «Sozlamalar» sahifasida (5 daqiqa) — ⚠️ hali bajarilmagan
> 8-noyabr holatiga `.env` da `TELEGRAM_BOT_TOKEN` va `TELEGRAM_ALLOWED_USER_IDS` bo'sh. Bot xizmati yoqilgan va
> token kiritilishini kutib turibdi — kiritishingiz bilan o'zi ishga tushadi.
1. Telegram'da **@BotFather** → `/newbot` → bot nomi → username. U bergan tokenni nusxalang. **YouTube botining tokenini ishlatmang.**
2. **@userinfobot** ga `/start` yozing — u ID raqamingizni beradi.
3. **http://localhost:8090** → parol bilan kiring → **Sozlamalar** → «Telegram» qadami: tokenni qo'ying,
   «Tekshirish»ni bosing (bot nomi chiqadi), ID'ni yozing → «Davom etish».
4. Yangi botingizga Telegram'da `/start` yozing.

## 2. Bot xizmati
`./install.sh` allaqachon ishga tushirilgan: sayt va bot fon xizmati sifatida ishlaydi va kompyuter yonganda o'zi
yoqiladi. Qayta o'rnatish yoki yangilash: `git pull && ./install.sh`. Tekshirish: `.venv/bin/python -m socialauto check`.

## 3. Sayt paroli
Parol `.env` faylida turibdi: `grep DASHBOARD_PASSWORD .env`. Sayt: **http://localhost:8090**.

## 4. Buffer API kaliti (5 daqiqa) — asosiy qadam
Bot tasdiqlangan reelni Buffer'da Instagram, YouTube va LinkedIn **navbatiga** qo'shadi, statistikani o'qiydi va reel
efirga chiqqanini aniqlaydi (story qoralamasi uchun). Chiqish vaqtini Buffer'dagi har bir kanalning **Posting schedule**
(navbat jadvali) belgilaydi — uni Buffer → kanal → Settings → Posting Schedule'da sozlang.
1. https://publish.buffer.com → **Settings → API** → **Create API key** (personal key). Bepul tarifda ham bor.
2. Saytda **Sozlamalar** → «Buffer» qadami: kalitni qo'ying va «Tekshirish»ni bosing (kanallaringiz nomi chiqadi).
3. Buffer'da **Instagram (Business/Creator)**, **YouTube** va **LinkedIn** kanallari ulangan bo'lsin (Buffer → Channels).
Saqlaganingizdan keyin bot o'zi qayta ishga tushadi.
Kalit bo'lmasa: tadqiqot statistikasiz ishlaydi va reellar Buffer'ga yuborilmaydi.

## 5. Sinov rejimini o'chirish (Buffer ulangandan keyin)
Sinov rejimida (`dry_run = true`) Buffer'ga hech narsa yuborilmaydi — faqat `data/dryrun_posts.json` ga yoziladi.
Tasdiqlangan reellar haqiqatda Buffer navbatiga tushishi uchun:
1. Loyiha papkasida: `python -m socialauto dry-run off` (Windows: `.venv\Scripts\python -m socialauto dry-run off`).
   Sozlama `config.local.toml` ga yoziladi (u sizniki, git'ga tushmaydi).
2. Bot va saytni qayta ishga tushiring: Linux `systemctl --user restart social-automation social-automation-web`;
   Windows `SocialAutomation-Bot` va `SocialAutomation-Web` vazifalarini to'xtatib, qayta ishga tushiring.

## 6. YouTube statistikasi (ixtiyoriy, 15 daqiqa) — faqat o'qish
Saytda **Sozlamalar → Statistika → YouTube**: u yerda qadamma-qadam ko'rsatma bor (Google Cloud loyihasi, ikkita API'ni
yoqish, «Desktop app» turidagi OAuth mijoz, JSON faylni yuklab olish). Faylni shu sahifada tanlang → «YouTube'ni
ulash» → kanalingizni tanlang → Allow. Ruxsat faqat **o'qish** uchun.

## 7. Instagram statistikasi (ixtiyoriy, 15 daqiqa) — faqat o'qish
Saytda **Sozlamalar → Statistika → Instagram**: Meta ilovangizning App ID va App Secret'ini qo'ying, sahifadagi
«Valid OAuth Redirect URI» manzilini Meta ilovangizga qo'shing va «Instagram'ni ulash» ni bosing. Instagram akkaunt
Business/Creator bo'lishi va Facebook sahifangizga bog'langan bo'lishi kerak.

## 8. Bepul video manbalari kalitlari (ixtiyoriy, 5 daqiqa)
Hozir B-roll Wikimedia Commons'dan olinadi (kalitsiz, litsenziyasi yozib boriladi). Ko'proq vertikal videolar uchun:
- Pexels: https://www.pexels.com/api/ → kalitni saytdagi **Sozlamalar** → «Qo'shimcha» ga qo'ying.
- Pixabay: https://pixabay.com/api/docs/ → kalitni o'sha joyga qo'ying.
Mixkit ishlatilmaydi (API yo'q). UzA rasmlari ishlatilmaydi (ruxsat kerak) — kelishuvingiz bo'lsa, ayting.

## 9. Ovozni qanday yozish (o'zbekcha matn, 45–60 soniya)
- Jim xonada, telefonni og'izdan 15–20 sm uzoqlikda, tabiiy ovozda o'qing; boshida 1 soniya jim turing.
- Botga **ovozli xabar** sifatida yuboring (audio fayl, dumaloq video yoki video ham bo'ladi, 20 MB gacha).
- Yangi ovoz yuborsangiz (video tasdiqlanmaguncha), eng oxirgisi ishlatiladi.

## 10. Muqova (har bir reel uchun)
Videoni tasdiqlaganingizdan keyin bot muqovani so'raydi. Muqovani o'zingiz tayyorlang (1080×1920, JPG/PNG) va
**fayl sifatida** yuboring (Telegram "rasm" sifatida yuborilsa, uni siqib yuboradi). Bot uni o'zgartirmaydi. Muqova
kelmaguncha reel "Muqova kutilmoqda" holatida turadi.

## 11. NavaiSTT va `align_voice.py` (agar sizda bo'lsa)
Bot hozir **rubaiSTT** (NavaiSTT'ning yangi nomi, o'sha muallif, o'zbekcha Whisper-medium, bepul) bilan ishlaydi. O'z
modelingiz yoki `align_voice.py` faylingiz bo'lsa, loyiha ichidagi `owner_files/` papkasiga tashlang — ulayman.

## 12. Caption uslubi
Bot uslubingizni Buffer'dagi oldingi postlaringizdan o'rganadi. Tezroq o'rgatish uchun 3–5 ta caption'ingizni
`data/style/caption_style.md` ga joylang.

## 13. Remotion litsenziyasi (bitta savol)
Remotion yakka shaxs va 3 kishigacha kompaniyalar uchun bepul. Kanal 4+ xodimli kompaniyaniki bo'lsa, ayting
(unda pullik litsenziya kerak; roziligingizsiz hech narsa sotib olinmaydi).

## 14. GitHub — kod reposi va kontent reposi
- **Kod reposi:** https://github.com/Abdurahman0/social-automation — faqat siz yozasiz; ilova (sizning kompyuteringizda
  ham, do'stlaringiznikida ham) undan faqat yangilanish oladi, unga hech narsa yozmaydi.
- **Kontent reposi:** https://github.com/Abdurahman0/social-automation-content (yopiq) — sizning reellaringiz shu
  yerga boradi (SSH orqali, `config.local.toml` da sozlangan). Hech narsa qilishingiz shart emas. Xohlasangiz, saytda
  Sozlamalar → GitHub'da akkauntingizni ham ulashingiz mumkin (rasmingiz va havolalar ko'rinadi).

## 15. Kod reposini OCHIQ (public) qilish va himoyalash (3 daqiqa) — ⚠️ MAJBURIY, faqat siz qila olasiz
**Nega:** repo hozir yopiq. Shuning uchun Windows'da `git clone` sizdan GitHub login so'radi; do'stlaringizdan ham
so'raydi. Ochiq qilingach hech kimdan login so'ralmaydi. Siz roziligingizni bergansiz; men to'xtagan joy — GitHub bu
uchta sozlama uchun sizning **2FA kodingizni** so'raydi (sudo rejimi), uni men kirita olmayman va aylanib o'tmayman.
Tarix to'liq tekshirildi va toza: sir, shaxsiy yo'l, reel/video/ovozingiz, `proof/`, joylash kodi yo'q
(`scripts/history_scan.sh`, natija `docs/TASK_07_REPORT.md` da).
1. https://github.com/Abdurahman0/social-automation/settings → eng pastda **Danger Zone → Change visibility →
   Change to public** → ogohlantirishlarni tasdiqlang → repo nomini yozing → **2FA kodi**.
2. **Settings → Collaborators** → «You haven't invited any collaborators yet» bo'lishi kerak (kimdir bo'lsa — Remove).
3. **Settings → Branches → Add classic branch protection rule** → *Branch name pattern*: `main` → «Allow force
   pushes» va «Allow deletions» **belgilanmagan** qolsin → **Create**. (Siz odatdagidek push qilaverasiz.)
4. Tekshirish (terminalda, loyiha papkasida): `scripts/verify_public.sh` → oxirida
   «RESULT: public — anyone can install without a GitHub login» chiqishi kerak.
5. Endi Windows'da shu bitta qator yetadi (PowerShell'ni oching):
   `irm https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.ps1 | iex`

Bilib qo'ying: ochiq repoda commitlar muallifi sifatida kompyuteringizdagi git sozlamasidagi ism va email ko'rinadi.

## 16. Javohir uchun (Doktor H₂O) — o'z kompyuterida, o'z akkauntlari bilan (Task 09)
Bu qadamlarni **Javohir o'zi** qiladi (sizning akkauntlaringiz kerak emas). Uning `the-suvyektiv-media` reposiga
ilova faqat yangi reel papkasini va `posted.md` ga bitta qatorni qo'shadi; boshqa fayllariga tegmaydi, `--force` yo'q.
1. **O'rnatish.** Linux/macOS terminalida:
   `curl -fsSL https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.sh | bash`
   Windows (PowerShell):
   `irm https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.ps1 | iex`
   Oxirida sayt ochiladi (http://localhost:8090) — parol o'ylab topib kiriting.
2. **Telegram.** @BotFather → `/newbot` → bot tokenini Sozlash → Telegram qadamiga qo'ying; o'z Telegram ID raqamingizni
   (@userinfobot) ham yozing. Bot faqat sizga yozadi.
3. **Buffer.** buffer.com'da Instagram (@suvyektiv), YouTube (Doktor H₂O) va LinkedIn'ni ulang → Settings → API →
   kalitni Sozlash → Buffer qadamiga qo'ying. Kanallaringiz ro'yxati chiqsa — tayyor.
4. **GitHub.** Sozlash → GitHub → «GitHub'ni ulash» → chiqqan qisqa kodni github.com/login/device ga kiriting →
   **Authorize** (eraliyev-j akkaunti bilan). Keyin **«Mavjud repomni ulash»** ni tanlang → ro'yxatdan
   **eraliyev-j/the-suvyektiv-media** ni bosing (yoki havolasini qo'ying). Repo kompyuterga videolarsiz yuklanadi
   (~50 MB); sahifada «Reellar «eraliyev-j/the-suvyektiv-media» reposiga boradi · 17 ta reel» ko'rinadi.
5. **Claude.** Sozlash → Claude → «Claude'ga kirish» → o'z Claude obunangiz bilan kiring (API kalit kerak emas).
6. **Sinov rejimi.** Hammasi ulangach, bir reelni sinab ko'ring; tayyor bo'lsangiz terminalda
   `python -m socialauto dry-run off` (sinov rejimida Buffer'ga ham, `posted.md` ga ham hech narsa yozilmaydi).

Shuni biling: bot sizning `brand/voice.md`, `guidance-book.md` va `doktor-h2o-*` skilllaringizni o'qiydi (faqat o'qiydi)
va ssenariyni ular bo'yicha yozadi: reel 30–45 soniya, raqamlar faqat manbadan, sizning CTA'ingiz. Yangi reel
`reels/<sana>-<mavzu>/reel.mp4`, `cover.jpg` (o'zingiz yuborgan muqova, o'zgarishsiz), `script.md` (soniyali ovoz
matni, manbalar, caption) bo'lib qo'shiladi. Agar shu payt o'zingiz ham repoga yozgan bo'lsangiz, bot sizning
o'zgarishingiz ustiga qo'shadi; to'qnashuv bo'lsa — reelni kompyuterda saqlab, Telegram'da aytadi.
