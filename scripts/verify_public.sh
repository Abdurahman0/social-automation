#!/usr/bin/env bash
# Proves that anyone can get the project with NO GitHub login (Task 07 §7). Run after the repo is public.
#   scripts/verify_public.sh [output-file]
set -uo pipefail
OUT="${1:-/tmp/social_task07/anonymous_clone.txt}"
mkdir -p "$(dirname "$OUT")"
exec > >(tee "$OUT") 2>&1
REPO="Abdurahman0/social-automation"
TMP="$(mktemp -d /var/tmp/anon-check.XXXX)"; trap 'rm -rf "$TMP"' EXIT
ok=0
echo "== 1. anonymous API: curl https://api.github.com/repos/$REPO (no token)"
code=$(curl -s -o "$TMP/api.json" -w '%{http_code}' "https://api.github.com/repos/$REPO")
echo "   HTTP $code, private=$(python3 -c "import json;print(json.load(open('$TMP/api.json')).get('private'))" 2>/dev/null)"
[ "$code" = 200 ] || ok=1
echo; echo "== 2. clone with NO credentials at all (empty HOME, no helper, no prompt, askpass=false)"
HOME="$TMP/home" GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false \
  git -c credential.helper= clone "https://github.com/$REPO.git" "$TMP/anon-clone" && \
  echo "   cloned: $(git -C "$TMP/anon-clone" log -1 --format='%h %s' | cut -c1-90)" || ok=1
echo; echo "== 3. the one-line installers are downloadable without a login"
for f in install.sh install.ps1; do
  printf '   %s: HTTP %s\n' "$f" "$(curl -s -o /dev/null -w '%{http_code}' "https://raw.githubusercontent.com/$REPO/main/$f")"
  [ "$(curl -s -o /dev/null -w '%{http_code}' "https://raw.githubusercontent.com/$REPO/main/$f")" = 200 ] || ok=1
done
echo; [ "$ok" = 0 ] && echo "RESULT: public — anyone can install without a GitHub login" || echo "RESULT: NOT public yet"
exit "$ok"
