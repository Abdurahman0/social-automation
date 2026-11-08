# TASK 07 hisoboti — har kim o'z nusxasi va o'z akkauntlari; egasining reposi faqat o'qiladi (2026-11-08)

## Eng muhimi — sizdan kerak bo'lgan bitta qadam (3 daqiqa)
Repo hali **yopiq**. Windows'da `git clone` sizdan login so'raganining sababi aynan shu. Uni ochiq qilish, `main`
himoyasi va hamkorlar tekshiruvi uchun GitHub sizning **2FA kodingizni** so'raydi ("sudo mode"). Hatto o'zimizning
OAuth ilovamizga API ruxsatini tasdiqlash ham shu kodni so'radi. Uni men kirita olmayman va aylanib o'tmayman, shuning
uchun shu yerda to'xtadim. Qadamlar: **docs/OWNER_TODO.md §15**. Qisqasi:
1. https://github.com/Abdurahman0/social-automation/settings → **Danger Zone → Change visibility → Change to public** → 2FA.
2. **Settings → Collaborators** — bo'sh bo'lishi kerak.
3. **Settings → Branches → Add classic branch protection rule** → `main` → «Allow force pushes» / «Allow deletions»
   belgilanmagan → **Create**.
4. Tekshirish: `scripts/verify_public.sh` → «RESULT: public — anyone can install without a GitHub login».

Shundan keyin **Windows'da o'rnatish — bitta qator** (PowerShell'ni oching):
```powershell
irm https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.ps1 | iex
```
Linux / macOS:
```bash
curl -fsSL https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.sh | bash
```

## 1. Kod reposi va kontent reposi (asosiy tuzatish)
- **Kod reposi** (`origin` = sizning `Abdurahman0/social-automation`) endi faqat yangilanish olish uchun. Ilova unga
  hech qachon commit yoki push qilmaydi. **Qattiq himoya** (`socialauto/content_repo.py`): har bir push oldidan manzil
  bitta ko'rinishga keltiriladi (https / ssh / git@ / tokenli URL / mahalliy papka). Agar u kod reposi, kod papkasining
  istalgan remote'i yoki kod papkasining o'zi bo'lsa, push **rad etiladi**. Bu har bir kompyuterda, sizda ham ishlaydi.
  Butun dasturda `git push` faqat shu faylda bor (buni test tekshiradi). Force-push hech qayerda yo'q.
- **Kontent reposi**: reellar (video, muqovangiz, ssenariy, tadqiqot, manbalar) `data/content-repo/` ga tushadi.
  Bu papka kod reposidan git-ignore qilingan. Undan foydalanuvchining **o'z** GitHub'iga push qilinadi:
  `<login>/social-automation-content`, yopiq. Repo yo'q bo'lsa, ilova uni o'zi yaratadi.
- **Siz uchun**: `Abdurahman0/social-automation-content` (yopiq) yaratildi va SSH orqali ulandi (`config.local.toml`).
  Birinchi push muvaffaqiyatli bo'ldi; kod reposiga push esa rad etildi. Eski `reels/` papkasi topilmadi, ko'chiriladigan
  narsa yo'q edi. Agar keyinchalik bo'lsa, bot uni ishga tushganda o'zi kontent reposiga ko'chiradi. GitHub'dagi kod
  tarixida reel / video / ovoz fayli yo'q (pastdagi skanga qarang).
- **`config.local.toml`** (git'ga tushmaydi) — shu kompyuterning o'z sozlamalari uchun (`dry_run`, kontent remote,
  YouTube kanal ID). `config.toml` kod reposidagidek o'zgarishsiz qoladi, shuning uchun yangilanish doim toza bo'ladi.

## 2. Hamma loginlar saytning ichida (Sozlash + Sozlamalar; har biri ikonli qadam, tekshirish tugmasi bilan)
Qadamlar: Parol → Telegram → Buffer → **GitHub** → **Claude** → **Statistika** → Qo'shimcha → Tayyor.
- **GitHub**: «GitHub'ni ulash» bosilganda sayt qisqa kod ko'rsatadi va github.com/login/device ni ochadi. Parol bu
  saytga yozilmaydi. Buning uchun akkauntingizda **«Social Automation» OAuth ilovasi** ochildi (device flow yoqilgan).
  Client ID `Ov23liS94MsnZzPLrzTA` `config.toml` da turadi — u ochiq identifikator, sir emas (device flow sirsiz
  ishlaydi). Haqiqiy device flow sinab ko'rildi: kod olindi, holat «kutilmoqda».
  - Muqobil yo'l: faqat kontent reposi uchun «Contents: read and write» huquqli fine-grained token. Qanday ochish
    sahifada ko'rsatilgan.
  - Ulangandan keyin: rasm, ism, @login, kontent reposiga havola ko'rinadi; «Uzish» tugmasi bor.
  - Token faqat `secrets/github.json` da (0600) saqlanadi. U saytga ham, loglarga ham chiqmaydi (testlar tekshiradi).
  - GitHub ulanmasa, reellar shu kompyuterda qoladi va sayt buni oddiy so'zlar bilan aytadi.
- **Claude**: «Claude'ga kirish» tugmasi shu kompyuter uchun `claude auth login` ni ishga tushiradi. Sahifada kirish
  havolasi va kod maydoni chiqadi; kirgandan keyin email va tarif ko'rinadi. API kalit yo'q. CLI o'rnatilmagan bo'lsa,
  shu OS uchun o'rnatish buyrug'i ko'rsatiladi.
  - Haqiqiy CLI bilan sinaldi, alohida vaqtinchalik papkada: havola chiqdi, noto'g'ri kod toza rad etildi, sizning
    loginingizga tegilmadi.
- **Instagram / YouTube**: bot hech qachon joylamaydi, shuning uchun bular qoralama va statistika uchun.
  - **Qoralamalar** — sizning Buffer'ingiz orqali. Buffer qadami ulangan Instagram / YouTube / LinkedIn kanallarini nomi
    va rasmi bilan ko'rsatadi, yonida «Buffer'da yana kanal ulash» havolasi bor.
  - **Statistika**: «Instagram'ni ulash» (o'z Meta ilovangiz bilan Meta login; sahifa Redirect URI'ni nusxalash tugmasi
    bilan beradi) va «YouTube'ni ulash» (o'z Google OAuth mijozingiz, faqat `.readonly` ruxsatlar). YouTube uchun
    qadamma-qadam ko'rsatma va JSON fayl tanlagich bor.
  - Ikkalasi ixtiyoriy. Saytda faqat akkaunt nomi ko'rinadi, tokenlar ko'rinmaydi.
  - Qaytish manzilini sizning cookie emas, bir martalik `state` qiymati himoyalaydi (15 daqiqa amal qiladi), chunki
    SameSite=Strict cookie boshqa saytdan qaytishda yuborilmaydi. Testlar soxta `state` rad etilishini va qayta
    ishlatib bo'lmasligini tekshiradi.
- **Telegram** qadami avvalgidek. Hamma sirlar faqat shu kompyuterda, saqlangach yashirin ko'rinadi, Sozlamalarda
  o'zgartiriladi.

## 3. Har doim ishlaydi
- Linux: systemd user xizmatlari + linger (kirmasdan oldin ham ishga tushadi), `After=network-online.target`.
  macOS: LaunchAgent (kirganda ishga tushadi).
- Windows: install.ps1 administrator sifatida ishga tushirilsa, vazifa kompyuter yonganda ishga tushadi (S4U,
  parol saqlanmaydi). Aks holda kirganda ishga tushadi va o'rnatuvchi buni aytadi.
- Internet yo'q bo'lsa: bot jim kutadi (bir marta logga yozadi). Sayt hamma sahifada **«Internet yo'q — kutyapman.
  Ulanish tiklanishi bilan hammasi o'zi davom etadi.»** deb ko'rsatadi.
- **Haqiqiy sinov shu kompyuterda** (`scripts/offline_check.sh`, natija `/tmp/social_task07/offline_check.txt`):
  - ikkala xizmat `enabled`, linger `yes`, `WantedBy=default.target`;
  - ikkala jarayon `kill -9` qilindi → systemd ularni qayta ko'tardi (`NRestarts=1`), sayt 200 qaytardi;
  - stop → start (qayta yoqilishdagi holat) → ikkalasi `active`, sayt 200;
  - **internet uzilgan holat**: bot va sayt alohida tarmoqsiz namespace'da (`unshare -rn`) ishga tushirildi. Bu
    usulda kompyuterning qolgan qismi, jumladan jonli YouTube boti, internetdan uzilmaydi. Natija: sayt
    `{"online":false}`; bot 20 soniya xatosiz kutdi va toza to'xtadi;
  - internet bor holatda kutish darhol tugadi.

## 4. Yangilanishlar (hamma uchun faqat o'qish)
Sozlamalar sahifasining tepasida yangilanish kartasi bor. Egasi yangi versiya chiqarsa, «Yangilanish bor: N ta
o'zgarish» yozuvi va o'zgarishlar ro'yxati chiqadi, yonida **«Yangilash»** tugmasi.
- Yangilash faqat `fetch` + `merge --ff-only` qiladi. U anonim ishlaydi (`credential.helper=` bo'sh, so'rovsiz).
  Push, reset va stash qila olmaydi (test tekshiradi).
- `.env`, `secrets/`, `data/` (kontent reposi bilan), `config.local.toml` ga tegilmaydi.
- Paketlar ro'yxati o'zgargan bo'lsa, pip / npm qayta o'rnatiladi. Keyin bot va sayt o'zi qayta ishga tushadi.
- Tarix ajralib ketgan yoki fayllar qo'lda o'zgartirilgan bo'lsa, yangilash bajarilmaydi, hech narsa o'zgarmaydi va
  sababi oddiy so'zlar bilan aytiladi.

## 5. Egasining reposi boshqalar uchun faqat o'qish
- README boshida: «Bu repoga faqat egasi yozadi. O'zingizniki uchun fork qilishingiz shart emas — o'rnating va o'z
  GitHub'ingizni ulang.» (inglizchasi ham bor).
- Bir qatorli o'rnatuvchi bilan klon qilingan nusxada `origin` ning push manzili
  `no-push:the-code-repo-is-read-only` bo'ladi, ya'ni push manzili umuman yo'q. Ilovaning o'zi ham kod reposiga
  yozmaydi.
- Ochiq qilish, `main` himoyasi va hamkorlar tekshiruvi sizning 2FA qadamingizni kutmoqda (yuqorida).
- **To'liq tarix skani** (`scripts/history_scan.sh main`, natija `/tmp/social_task07/history_scan.txt`):
  - gitleaks: `no leaks found`. Dastlab soxta topilmalar chiqdi: ochiq OAuth client id va bir test paroli. Ular
    `gitleaks:allow` bilan belgilandi, GitHub'ga hali chiqmagan mahalliy commitlar bitta toza commitga birlashtirildi;
  - shaxsiy yo'l yoki foydalanuvchi nomi: 0 ta;
  - media: faqat `tests/fixtures/sample_voice_*.wav` — 4 ta sintetik sinov ovozi (`scripts/make_test_voice*.py`),
    sizning ovozingiz emas;
  - `reels/` va `proof/` yo'q; joylash kodi hech bir commitda yo'q;
  - **RESULT: clean — safe to publish**.

## 6. Bir qatorli o'rnatuvchilar (§7 qo'shimcha)
- `install.ps1` `irm … | iex` bilan ishga tushirilsa (diskda hali fayl yo'q):
  - Git yo'q bo'lsa, winget bilan o'rnatadi;
  - kodni ochiq HTTPS orqali `%USERPROFILE%\social-automation` ga klon qiladi. `credential.helper=` bo'sh bo'lgani
    uchun Git Credential Manager oynasi ochilmaydi, login so'ralmaydi;
  - push manzilini o'chiradi;
  - keyin haqiqiy o'rnatuvchini ishga tushiradi;
  - `exit` emas, `return` ishlatadi, shuning uchun sizning PowerShell oynangiz yopilmaydi.
- `install.sh` `curl | bash` bilan ham xuddi shunday ishlaydi. Git o'rnatish: Homebrew, Command Line Tools yoki
  apt / dnf / pacman.
- **Isbot**:
  - Linux'da to'liq bir qatorli o'rnatish: bo'sh HOME, hech qanday login yo'q (`GIT_ASKPASS=/bin/false`), repoga
    mahalliy nusxa (`SA_REPO_URL`) orqali. Natija: 8 qadam ✓, klonda push manzili yo'q
    (`/tmp/social_task07/oneliner_install.txt`).
  - Windows yo'li PowerShell 7'da `Get-Content install.ps1 -Raw | Invoke-Expression` bilan sinaldi (dry-run):
    anonim klon qilindi, oyna ochiq qoldi, push manzili yo'q (`/tmp/social_task07/oneliner_windows_dryrun.txt`).
- **Anonim klon — hozircha muvaffaqiyatsiz** (repo yopiq), aynan siz ko'rgan xato:
  ```
  == 1. anonymous API: curl https://api.github.com/repos/Abdurahman0/social-automation (no token)
     HTTP 404
  == 2. clone with NO credentials at all (empty HOME, no helper, no prompt, askpass=false)
  fatal: could not read Username for 'https://github.com': terminal prompts disabled
  RESULT: NOT public yet
  ```
  §15 qadamidan keyin `scripts/verify_public.sh` ni ishga tushiring. U HTTP 200, muvaffaqiyatli anonim klon va
  ikkala o'rnatuvchining yuklanishini ko'rsatishi kerak.

## 7. Ikkinchi foydalanuvchi sinovi (`scripts/second_user_check.sh`, natija `/tmp/social_task07/second_user.txt`)
Sinov: alohida HOME, git identifikatori yo'q. «Egasining GitHub'i» va «do'stning GitHub'i» — ikkita mahalliy bare repo.
- Do'st reel e'lon qildi → u **o'zining** reposiga tushdi (`reels/2026-11-12-suv-tejash/…`). Commit muallifi
  «Social Automation» bo'ldi, chunki kompyuterda git identifikatori yo'q edi.
- Egasining reposiga push qilishning uch xil urinishi (SSH, `origin` papkasi, katta-kichik harfi boshqa https) — uchalasi
  ham **rad etildi**.
- Egasi yangi versiya push qildi → do'st yangiladi (fast-forward). Uning `.env` va `config.local.toml` fayllari
  o'zgarmadi, kontent reposi joyida qoldi.
- Egasining reposida faqat egasining o'z push'i bor, yangi branch yo'q, `reels/` yo'q.

## 8. Testlar va skrinshotlar
- **163 ta test o'tdi**. Yangi test fayllari: `test_content_repo.py`, `test_accounts.py`, `test_updater.py`,
  `test_bootstrap.py` va qo'shimcha runner testlari. Ular tekshiradi:
  - kod reposiga push rad etiladi, kontent kontent reposiga tushadi;
  - yangilanish faqat fast-forward va foydalanuvchi ma'lumotiga tegmaydi;
  - tokenlar HTML va loglarda ko'rinmaydi;
  - Instagram qaytish manzili soxta `state` ni rad etadi;
  - YouTube fayli tekshiriladi va 0600 bilan saqlanadi;
  - bir qatorli o'rnatuvchilar anonim ishlaydi;
  - internet kutish va yangilanishdan keyingi qayta ishga tushish ishlaydi.
- Sinov paytida topilgan muhim xato: testlar shu kompyuterning `config.local.toml` faylini o'qib, sizning kontent
  remote'ingizni olgan edi. Push'lar rad etildi, kontent reposingiz o'zgarmadi (tekshirildi). Endi testlar o'z
  `config.toml` nusxasidan foydalanadi va kontent remote yo'qligini tekshiradi.
- **Skrinshotlar** (`/tmp/social_task07/`; telefon, planshet, kompyuter × yorug', qorong'i; soxta sinov akkauntlari
  bilan, haqiqiy token ishlatilmagan):
  - 60 ta Sozlamalar sahifasi skrinshoti: Buffer kanallari; GitHub (ulanmagan, kod, ulangan); Claude (kirilmagan,
    havola + kod, kirilgan); Statistika; GitHub sahifasi; «Internet yo'q» banneri;
  - 54 ta birinchi ishga tushirish (8 qadam) skrinshoti;
  - avtomatik maket tekshiruvi: **114/114 muammosiz**;
  - README uchun 6 tasi `docs/images/` da.

## 9. Bu yerda tekshirib bo'lmaganlar
- **Windows va macOS** faqat kod bo'yicha tekshirildi:
  - PowerShell parser: `install.ps1` va `windows_service.ps1` da 0 xato;
  - bootstrap PowerShell 7'da `iex` orqali sinaldi;
  - shellcheck xato topmadi.
  Haqiqiy Windows'dagi winget, Task Scheduler (S4U) va macOS'dagi launchd bu yerda ishga tushirilmadi.
- Haqiqiy Instagram / YouTube / GitHub loginining oxirigacha o'tishi sizning akkauntlaringiz va 2FA kodingizni talab
  qiladi. Kod soxta serverlar bilan to'liq sinaldi; GitHub device flow'ning boshlanishi haqiqiy GitHub bilan sinaldi.
- Repo ochiq qilinmaguncha bir qatorli o'rnatuvchi ishlamaydi (§15).

## Yuklangan commit
Hisobot bilan birga oxirgi commit `main` ga push qilindi; mahalliy `main` va GitHub'dagi `main` bir xil ekani push'dan
keyin tekshirildi (hash yakuniy xabarda).
