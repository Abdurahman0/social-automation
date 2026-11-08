#!/usr/bin/env bash
# Task 07 check (Linux): the services survive a crash/restart and start at boot, and with NO internet the bot waits
# quietly and the website reports "offline" instead of failing. The network is cut only for the processes under
# test (an unprivileged network namespace, `unshare -rn`), never for the rest of this computer.
#
#   scripts/offline_check.sh [output-file]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-/tmp/social_task07/offline_check.txt}"
mkdir -p "$(dirname "$OUT")"
PY="$ROOT/.venv/bin/python"
exec > >(tee "$OUT") 2>&1
say() { printf '\n== %s\n' "$1"; }

say "1. Boot: units enabled for the user session, linger on (they start when the computer turns on)"
for u in social-automation.service social-automation-web.service; do
  printf '  %s: enabled=%s active=%s\n' "$u" "$(systemctl --user is-enabled "$u")" "$(systemctl --user is-active "$u")"
done
printf '  linger: %s\n' "$(loginctl show-user "$USER" -p Linger --value)"
printf '  wanted by: %s\n' "$(systemctl --user show social-automation.service -p WantedBy --value)"

say "2. Crash: kill -9 both main processes; systemd must start them again"
for u in social-automation.service social-automation-web.service; do
  pid=$(systemctl --user show "$u" -p MainPID --value)
  kill -9 "$pid" 2>/dev/null && echo "  killed $u (pid $pid)"
done
sleep 12
for u in social-automation.service social-automation-web.service; do
  printf '  %s: active=%s new pid=%s restarts=%s\n' "$u" "$(systemctl --user is-active "$u")" \
    "$(systemctl --user show "$u" -p MainPID --value)" "$(systemctl --user show "$u" -p NRestarts --value)"
done
printf '  website answers: %s\n' "$(curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/session)"

say "3. Stop/start (what a reboot does to the services)"
systemctl --user stop social-automation.service social-automation-web.service
printf '  after stop: %s %s\n' "$(systemctl --user is-active social-automation.service)" "$(systemctl --user is-active social-automation-web.service)"
systemctl --user start social-automation.service social-automation-web.service
for _ in $(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:8090/api/session 2>/dev/null && break; sleep 1; done
printf '  after start: %s %s, website: %s\n' "$(systemctl --user is-active social-automation.service)" \
  "$(systemctl --user is-active social-automation-web.service)" "$(curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/api/session)"

say "4. No internet: a temporary copy of the settings, bot and website inside a network namespace without network"
TMP="$(mktemp -d /var/tmp/sa-offline.XXXX)"
cp "$ROOT/config.toml" "$TMP/"
printf 'TELEGRAM_BOT_TOKEN=123456789:AAH%s\nTELEGRAM_ALLOWED_USER_IDS=111\nDASHBOARD_PASSWORD=offline-test-1\n' "$(printf 'x%.0s' $(seq 1 32))" > "$TMP/.env"
cat > "$TMP/run.py" <<EOF
import sys, threading, time, json, urllib.request
sys.path.insert(0, "$ROOT")
from pathlib import Path
from socialauto.config import load_settings
from socialauto.web.server import create_app
import uvicorn, logging
logging.basicConfig(level=logging.INFO, format="  [%(name)s] %(message)s")
s = load_settings(Path("$TMP/config.toml"), Path("$TMP/.env"), root=Path("$TMP"))
srv = uvicorn.Server(uvicorn.Config(create_app(s), host="127.0.0.1", port=8191, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start()
time.sleep(3)
print("  website /api/net:", urllib.request.urlopen("http://127.0.0.1:8191/api/net").read().decode())
from socialauto.netcheck import wait_until_online
stop = threading.Event()
t = threading.Thread(target=wait_until_online, kwargs={"stop": stop, "every": 5, "log": logging.getLogger("socialauto.bot")}, daemon=True)
t.start(); time.sleep(20)
print("  bot still waiting after 20 s (no crash, no error spam):", t.is_alive())
stop.set(); t.join(6)
print("  stopped cleanly:", not t.is_alive())
EOF
unshare -rn sh -c "ip link set lo up 2>/dev/null; '$PY' '$TMP/run.py'"
rm -rf "$TMP"

say "5. Internet back: the same wait returns as soon as the network answers (this computer is online)"
"$PY" -c "
import sys; sys.path.insert(0, '$ROOT')
from socialauto.netcheck import wait_until_online, online
print('  online:', online(max_age=0), '| wait returns:', wait_until_online(every=1))"
echo
echo "Done."
