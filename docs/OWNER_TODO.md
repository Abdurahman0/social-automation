# Egasi qiladigan ishlar (faqat siz qila oladigan qadamlar)

Qolgan hamma narsa tayyor va sinov rejimida (dry-run) ishlab turibdi. Har bir qadam — "shuni bosing / shuni joylang".
Terminal buyruqlari loyiha papkasida (`social-automation`) yoziladi.

**Muhim qonunlar (siz belgilagansiz):** bot **hech qachon o'zi joylamaydi yoki rejalashtirmaydi** — faqat Buffer'da
qoralama (va story qoralamasi) tayyorlaydi; tasdiqlab rejalashtirish sizda. Bot **muqova qilmaydi** — muqovani siz
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
Bot Buffer'da Instagram, YouTube va LinkedIn uchun **qoralama** yaratadi, statistikani o'qiydi va siz rejalashtirgan reel
efirga chiqqanini aniqlaydi (story qoralamasi uchun). U hech narsani o'zi rejalashtirmaydi yoki chiqarmaydi.
1. https://publish.buffer.com → **Settings → API** → **Create API key** (personal key). Bepul tarifda ham bor.
2. Saytda **Sozlamalar** → «Buffer» qadami: kalitni qo'ying va «Tekshirish»ni bosing (kanallaringiz nomi chiqadi).
3. Buffer'da **Instagram (Business/Creator)**, **YouTube** va **LinkedIn** kanallari ulangan bo'lsin (Buffer → Channels).
Saqlaganingizdan keyin bot o'zi qayta ishga tushadi.
Kalit bo'lmasa: tadqiqot statistikasiz ishlaydi va qoralamalar yaratilmaydi.

## 5. Sinov rejimini o'chirish (Buffer ulangandan keyin)
Sinov rejimida (`dry_run = true`) Buffer qoralamalari haqiqatda yaratilmaydi — faqat `data/dryrun_posts.json` ga
yoziladi. Buffer'da haqiqiy **qoralamalar** paydo bo'lishini xohlasangiz:
1. `config.toml` da: `dry_run = false`
2. `systemctl --user restart social-automation`
Shunda ham bot hech narsani rejalashtirmaydi yoki chiqarmaydi — qoralamani ochib, tasdiqlab rejalashtirish sizda.

## 6. YouTube statistikasi (ixtiyoriy, 15 daqiqa) — faqat o'qish
Saytdagi YouTube raqamlari uchun. Ruxsat faqat **o'qish** uchun so'raladi (yuklash ruxsati yo'q).
1. https://console.cloud.google.com → **New project** → nom: `social-automation` → **Create**.
2. **APIs & Services → Library**: **"YouTube Data API v3"** → **Enable**; **"YouTube Analytics API"** → **Enable**.
3. **OAuth consent screen** → **External** → app nomi, emailingiz → **Test users** ga o'z emailingiz → oxirida
   **"Publish app" → "In production"** (aks holda ruxsat har 7 kunda tugaydi; "tasdiqlanmagan ilova" ogohlantirishida
   **Advanced → Continue**).
4. **Credentials → Create credentials → OAuth client ID** → **Desktop app** → **Create** → **Download JSON**.
5. `mv ~/Downloads/client_secret_*.json secrets/youtube_client_secret.json && chmod 600 secrets/youtube_client_secret.json`
6. `.venv/bin/python -m socialauto youtube-auth` → brauzerda kanalingizni tanlang → **Allow**.

## 7. Instagram statistikasi (ixtiyoriy, 15 daqiqa) — faqat o'qish
1. Instagram → **Settings → Account type and tools → Switch to professional account** → **Creator** yoki **Business**,
   va Facebook sahifangizga bog'lang.
2. https://developers.facebook.com → **My Apps → Create app** (Business) → **App settings → Basic**: App ID va App Secret
   ni saytdagi **Sozlamalar** → «Qo'shimcha» qadamiga qo'ying.
3. https://developers.facebook.com/tools/explorer → ilovangiz → **Get User Access Token** → faqat shu ruxsatlar:
   `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement` → **Generate** → nusxalang.
4. `.venv/bin/python -m socialauto instagram-connect` → tokenni qo'ying. Token o'zi yangilanib turadi.

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

## 14. GitHub repo
Bo'sh repo oching va havolasini yuboring. Har tasdiqlangan reel `reels/<sana>-<mavzu>/` ga (video, muqovangiz,
tadqiqot, ssenariy, manbalar) yuklanadi; 50 MB dan katta video Git LFS bilan. Repo ulanguncha bular shu kompyuterda
saqlanadi va saytda "kutilmoqda" deb ko'rinadi.
