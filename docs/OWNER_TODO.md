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
1. Loyiha papkasidagi `config.local.toml` fayliga (u sizniki, git'ga tushmaydi) eng yuqoriga shu qatorni yozing:
   `dry_run = false`
2. `systemctl --user restart social-automation`
Shunda ham bot hech narsani rejalashtirmaydi yoki chiqarmaydi — qoralamani ochib, tasdiqlab rejalashtirish sizda.

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

## 15. Kod reposini ochiq (public) qilish va himoyalash (5 daqiqa) — ⚠️ siz qilasiz
GitHub bu sozlamalar uchun sizdan 2FA kodini so'raydi (sudo rejimi), shuning uchun ularni men qila olmayman.
Tarix tekshirildi: sir, shaxsiy yo'l, reel/video/ovozingiz, `proof/` va joylash kodi yo'q (`docs/TASK_07_REPORT.md`).
1. **Hamkorlar yo'qligini tekshiring:** repo → **Settings → Collaborators** → «You haven't invited any collaborators
   yet» deb turishi kerak. Kimdir bo'lsa — **Remove**.
2. **Ochiq qilish:** **Settings → General** → eng pastda **Danger Zone → Change visibility → Change to public** →
   ogohlantirishlarni o'qib tasdiqlang → repo nomini yozing → 2FA kodi.
3. **main'ni himoyalash** (ochiq bo'lgach bepul): **Settings → Branches → Add classic branch protection rule** →
   *Branch name pattern*: `main` → «Allow force pushes» va «Allow deletions» **belgilanmagan** holda qoldiring →
   **Create**. (Boshqa hech narsa shart emas — siz odatdagidek push qilaverasiz, faqat force-push va o'chirish yopiladi.)
4. Bilib qo'ying: ochiq repoda commitlar muallifi sifatida kompyuteringizdagi git sozlamasidagi ism va email
   ko'rinadi (bu odatiy holat; xohlasangiz, kelgusi commitlar uchun GitHub'ning «noreply» emailini qo'yish mumkin).
