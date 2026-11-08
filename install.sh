#!/usr/bin/env bash
# Social Automation — one-command installer for Linux and macOS.
#
#   ./install.sh               install or update (safe to run again after `git pull`)
#   ./install.sh --uninstall   stop and remove the background services (your files and .env stay)
#   ./install.sh --no-service  install everything but do not register background services
#   ./install.sh --no-open     do not open the browser at the end
#
# One line, no git login and no GitHub account needed (the repo is public):
#   curl -fsSL https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.sh | bash
# It installs git if needed, clones over public HTTPS into ~/social-automation (SA_DIR to change) and continues.
#
# Messages are in Uzbek, then English. Nothing here prints a token or a password.
set -euo pipefail

REPO_URL="${SA_REPO_URL:-https://github.com/Abdurahman0/social-automation.git}"   # SA_REPO_URL: a mirror (tests)

bootstrap() {   # run from `curl | bash`: get the code first (anonymously), then run the real installer from it
  local dir="${SA_DIR:-$HOME/social-automation}"
  printf '\n==> Social Automation: kod yuklanmoqda / downloading the code → %s\n' "$dir"
  if ! command -v git >/dev/null 2>&1; then
    if [ "$(uname -s)" = Darwin ]; then
      if command -v brew >/dev/null 2>&1; then brew install git >/dev/null
      else xcode-select --install 2>/dev/null || true
        echo "  ! git kerak / git is needed: o'rnatish oynasi ochildi — tugagach shu buyruqni qayta ishga tushiring." >&2
        echo "    (the Command Line Tools installer opened — run this command again when it finishes)" >&2; exit 1; fi
    elif command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then sudo apt-get install -y git >/dev/null
    elif command -v dnf >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then sudo dnf install -y git >/dev/null
    elif command -v pacman >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then sudo pacman -S --noconfirm git >/dev/null
    else echo "  ! git topilmadi / git not found: install git, then run this command again." >&2; exit 1; fi
  fi
  # Never a login prompt: no credential helper, no terminal prompt, public HTTPS only.
  local g=(git -c credential.helper= -c core.askPass=)
  if [ -d "$dir/.git" ]; then
    GIT_TERMINAL_PROMPT=0 "${g[@]}" -C "$dir" pull --ff-only --quiet
  else
    GIT_TERMINAL_PROMPT=0 "${g[@]}" clone --quiet "$REPO_URL" "$dir"
  fi
  # The owner's repo is read-only for everyone else: this copy gets no push address at all.
  git -C "$dir" remote set-url --push origin "no-push:the-code-repo-is-read-only"
  if [ -n "${SA_BOOTSTRAP_DRYRUN:-}" ]; then echo "  [OK] cloned anonymously; next: $dir/install.sh"; exit 0; fi
  exec bash "$dir/install.sh" "$@"
}

SELF="${BASH_SOURCE[0]:-}"
if [ -z "$SELF" ] || [ ! -f "$(dirname "$SELF")/socialauto/__init__.py" ]; then
  bootstrap "$@"
fi
ROOT="$(cd "$(dirname "$SELF")" && pwd)"
cd "$ROOT"
OS="$(uname -s)"
PORT=8090
SERVICE=1
OPEN=1
UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    --uninstall) UNINSTALL=1 ;;
    --no-service) SERVICE=0 ;;
    --no-open) OPEN=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Noma'lum parametr / unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; N=$'\033[0m'; else B=""; G=""; R=""; Y=""; N=""; fi
step() { printf '\n%s==> %s%s\n' "$B" "$1" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$1"; }
die()  { printf '\n  %s✗ %s%s\n' "$R" "$1" "$N" >&2; [ $# -gt 1 ] && printf '    %s\n' "${@:2}" >&2; exit 1; }
trap 'die "Kutilmagan xato / unexpected error (line $LINENO)." "Xabarni o'"'"'qing va o'"'"'rnatuvchini qayta ishga tushiring / read the message above and run ./install.sh again."' ERR

case "$OS" in
  Linux|Darwin) ;;
  *) die "Bu skript Linux va macOS uchun / this script is for Linux and macOS." "Windows: install.ps1" ;;
esac

# Law 9: heavy steps run inside a memory cap on Linux when systemd is there; elsewhere they run as they are.
heavy() {
  if [ "$OS" = Linux ] && command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue -- "$@"
  else
    "$@"
  fi
}

LINUX_UNITS="social-automation.service social-automation-web.service"
MAC_AGENTS="com.socialautomation.bot com.socialautomation.web"
UNIT_DIR="$HOME/.config/systemd/user"
AGENT_DIR="$HOME/Library/LaunchAgents"
has_user_systemd() { [ "$OS" = Linux ] && command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; }

remove_services() {
  if [ "$OS" = Linux ]; then
    if has_user_systemd; then
      for u in $LINUX_UNITS; do systemctl --user disable --now "$u" >/dev/null 2>&1 || true; rm -f "$UNIT_DIR/$u"; done
      systemctl --user daemon-reload
    fi
  else
    for a in $MAC_AGENTS; do
      launchctl bootout "gui/$(id -u)/$a" >/dev/null 2>&1 || true
      rm -f "$AGENT_DIR/$a.plist"
    done
  fi
}

if [ "$UNINSTALL" = 1 ]; then
  step "Fon xizmatlari o'chirilmoqda / removing the background services"
  remove_services
  ok "Xizmatlar to'xtatildi va o'chirildi / services stopped and removed"
  echo "  Loyiha papkasi, .env va ma'lumotlar joyida qoldi. To'liq o'chirish uchun papkani o'chiring."
  echo "  The project folder, .env and data are kept. Delete the folder to remove everything."
  exit 0
fi

pm_hint() {   # how to install a package on this computer
  if [ "$OS" = Darwin ]; then echo "brew install $2"
  elif command -v apt-get >/dev/null 2>&1; then echo "sudo apt-get install -y $1"
  elif command -v dnf >/dev/null 2>&1; then echo "sudo dnf install -y $1"
  elif command -v pacman >/dev/null 2>&1; then echo "sudo pacman -S $1"
  else echo "$1 ni tizimingiz paket menejeri bilan o'rnating / install $1 with your package manager"; fi
}
brew_try() {  # macOS: install with Homebrew automatically when it is there
  [ "$OS" = Darwin ] && command -v brew >/dev/null 2>&1 && { brew install "$1" >/dev/null && return 0; }
  return 1
}

# ------------------------------------------------------------------------------------------------ 1. tools
step "1/8 Kerakli dasturlar tekshirilmoqda / checking required programs"
py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }
PY=""
if [ -x .venv/bin/python ] && py_ok .venv/bin/python; then PY=.venv/bin/python
else
  for c in python3.13 python3.12 python3.11 python3.14 python3; do
    if command -v "$c" >/dev/null 2>&1 && py_ok "$c"; then PY="$(command -v "$c")"; break; fi
  done
fi
if [ -z "$PY" ] && brew_try python@3.12; then PY="$(brew --prefix)/bin/python3.12"; fi
[ -n "$PY" ] || die "Python 3.11+ topilmadi / Python 3.11 or newer not found." "$(pm_hint "python3 python3-venv" python@3.12)"
ok "Python: $("$PY" --version 2>&1)"

if ! command -v ffmpeg >/dev/null 2>&1; then brew_try ffmpeg || die "ffmpeg topilmadi / ffmpeg not found." "$(pm_hint ffmpeg ffmpeg)"; fi
ok "ffmpeg: $(ffmpeg -version | head -n1 | cut -d' ' -f1-3)"

node_ok() { command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 && \
  [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 18 ]; }
if ! node_ok; then brew_try node || true; fi
node_ok || die "Node.js 18+ topilmadi / Node.js 18 or newer not found (needed for the video renderer)." \
  "$(pm_hint "nodejs npm" node)" "yoki / or: https://nodejs.org"
ok "Node.js: $(node --version)"

# ------------------------------------------------------------------------------------------------ 2. Python
step "2/8 Python muhiti / Python environment (.venv)"
if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv .venv || die "venv yaratib bo'lmadi / could not create the virtual environment." "$(pm_hint python3-venv python@3.12)"
fi
heavy .venv/bin/python -m pip install -q --disable-pip-version-check --upgrade pip
heavy .venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt \
  || die "Python paketlarini o'rnatib bo'lmadi / could not install the Python packages." "Internetni tekshirib qayta ishga tushiring / check the internet and run ./install.sh again."
ok "Python paketlari o'rnatildi / Python packages installed"

# ------------------------------------------------------------------------------------------------ 3. Remotion
step "3/8 Video chizuvchi (Remotion) / video renderer (Remotion)"
( cd remotion && heavy npm install --no-audit --no-fund --loglevel=error >/dev/null ) \
  || die "npm paketlarini o'rnatib bo'lmadi / npm install failed." "Internetni tekshirib qayta ishga tushiring / check the internet and run ./install.sh again."
( cd remotion && heavy npx --no-install remotion browser ensure >/dev/null ) \
  || die "Remotion brauzerini yuklab bo'lmadi / could not download Remotion's browser." "Qayta ishga tushiring / run ./install.sh again."
ok "Remotion tayyor / Remotion ready"

# ------------------------------------------------------------------------------------------------ 4. model
step "4/8 O'zbekcha nutq modeli (~800 MB) / Uzbek speech model (~800 MB)"
heavy .venv/bin/python -m socialauto download-model || die "Model yuklanmadi / the model was not downloaded." "Qayta ishga tushiring / run ./install.sh again."

# ------------------------------------------------------------------------------------------------ 5. optional tunnel
step "5/8 cloudflared (ixtiyoriy / optional)"
cf_name=""
case "$OS-$(uname -m)" in
  Linux-x86_64) cf_name=cloudflared-linux-amd64 ;;
  Linux-aarch64|Linux-arm64) cf_name=cloudflared-linux-arm64 ;;
  Darwin-x86_64) cf_name=cloudflared-darwin-amd64.tgz ;;
  Darwin-arm64) cf_name=cloudflared-darwin-arm64.tgz ;;
esac
if [ -x bin/cloudflared ] || command -v cloudflared >/dev/null 2>&1; then ok "cloudflared bor / already installed"
elif [ -n "$cf_name" ] && command -v curl >/dev/null 2>&1; then
  mkdir -p bin
  url="https://github.com/cloudflare/cloudflared/releases/latest/download/$cf_name"
  if curl -fsSL -o "bin/$cf_name.part" "$url"; then
    if [ "${cf_name%.tgz}" != "$cf_name" ]; then tar -xzf "bin/$cf_name.part" -C bin cloudflared && rm -f "bin/$cf_name.part"
    else mv "bin/$cf_name.part" bin/cloudflared; fi
    chmod +x bin/cloudflared && ok "cloudflared o'rnatildi / installed"
  else rm -f "bin/$cf_name.part"; warn "cloudflared yuklanmadi — shart emas / not downloaded — optional, skipped"; fi
else warn "cloudflared o'tkazib yuborildi — shart emas / skipped — optional"; fi

# ------------------------------------------------------------------------------------------------ 6. settings file
step "6/8 Sozlamalar fayli / settings file (.env)"
if [ ! -f .env ]; then cp .env.example .env; ok ".env yaratildi / created (kalitlar saytdagi Sozlash sahifasida kiritiladi / keys are entered on the Setup page)"
else ok ".env bor, tegilmadi / exists, left as is"; fi
chmod 600 .env
mkdir -p secrets data logs && chmod 700 secrets

# ------------------------------------------------------------------------------------------------ 7. Claude
step "7/8 Claude Code (har kim o'z akkaunti bilan / each user's own account)"
if command -v claude >/dev/null 2>&1; then
  if claude auth status --json 2>/dev/null | grep -q '"loggedIn": *true'; then ok "Claude Code o'rnatilgan va kirilgan / installed and logged in"
  else warn "Claude Code'ga kirilmagan / not logged in. Terminalda 'claude' yozing va o'z akkauntingiz bilan kiring / type 'claude' and log in with your account."; fi
else
  warn "Claude Code o'rnatilmagan / not installed: npm install -g @anthropic-ai/claude-code  — keyin 'claude' yozib kiring / then type 'claude' and log in."
fi

# ------------------------------------------------------------------------------------------------ 8. services
step "8/8 Fon xizmatlari / background services"
mkdir -p logs
VPY="$ROOT/.venv/bin/python"
SVC_PATH="$ROOT/bin:$ROOT/.venv/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
if [ "$SERVICE" = 0 ]; then
  warn "--no-service: xizmatlar ro'yxatdan o'tkazilmadi / services not registered. Qo'lda / by hand: .venv/bin/python -m socialauto web  va/and  .venv/bin/python -m socialauto run"
elif [ "$OS" = Linux ]; then
  has_user_systemd || die "systemd user xizmatlari ishlamayapti / systemd user services are not available." "./install.sh --no-service bilan o'rnating va qo'lda ishga tushiring / use --no-service and start by hand."
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/social-automation.service" <<EOF
[Unit]
Description=Social Automation — Telegram bot and reel pipeline (Buffer drafts only, never posts)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
Environment=PATH=$SVC_PATH
UnsetEnvironment=ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN CLAUDE_CONFIG_DIR
ExecStart=$VPY -m socialauto run
# Exit code 75 = .env changed on the Setup page: start again at once with the new values.
Restart=always
RestartSec=3
TimeoutStopSec=60
MemoryMax=3G
MemorySwapMax=1G
OOMPolicy=continue
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
  cat > "$UNIT_DIR/social-automation-web.service" <<EOF
[Unit]
Description=Social Automation — website (http://localhost:$PORT)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
Environment=PATH=$SVC_PATH
ExecStart=$VPY -m socialauto web
Restart=always
RestartSec=5
MemoryMax=600M
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  # shellcheck disable=SC2086
  systemctl --user enable $LINUX_UNITS >/dev/null 2>&1
  # shellcheck disable=SC2086
  systemctl --user restart $LINUX_UNITS
  loginctl enable-linger "$USER" >/dev/null 2>&1 || true
  ok "systemd xizmatlari ishga tushdi / systemd services started (kompyuter yonganda o'zi ishlaydi / start at boot)"
else
  mkdir -p "$AGENT_DIR"
  for kind in bot web; do
    cmd=run; [ "$kind" = web ] && cmd=web
    plist="$AGENT_DIR/com.socialautomation.$kind.plist"
    cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.socialautomation.$kind</string>
  <key>ProgramArguments</key><array><string>$VPY</string><string>-m</string><string>socialauto</string><string>$cmd</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$SVC_PATH</string><key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$ROOT/logs/launchd-$kind.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/launchd-$kind.log</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)/com.socialautomation.$kind" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$plist"
  done
  ok "launchd agentlari ishga tushdi / launchd agents started (kirganingizda o'zi ishlaydi / start at login)"
fi

URL="http://localhost:$PORT/setup"
if [ "$SERVICE" = 1 ]; then
  for _ in $(seq 1 30); do curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/session" 2>/dev/null && break; sleep 1; done
fi
printf '\n%sTayyor! / Done!%s Sozlash sahifasi / Setup page: %s\n' "$G$B" "$N" "$URL"
echo "  Sinov rejimi yoqiq (dry_run): Buffer qoralamalari faqat yozib qo'yiladi. Bot hech qachon o'zi joylamaydi."
echo "  Dry-run is on: Buffer drafts are only recorded. The bot never posts anything by itself."
if [ "$OPEN" = 1 ] && [ "$SERVICE" = 1 ]; then
  if [ "$OS" = Darwin ]; then open "$URL" >/dev/null 2>&1 || true
  elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true; fi
fi
