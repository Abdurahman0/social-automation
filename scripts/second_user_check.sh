#!/usr/bin/env bash
# Task 07 check: a second user (own HOME, no git identity) installs from "the owner's repo", publishes a reel and
# updates — his content lands in HIS repo, the owner's repo is never written. Both "GitHubs" are local bare repos:
#   upstream.git  = the owner's code repo (a bare copy of this repo's main branch)
#   friend.git    = the friend's own content repo
#
#   scripts/second_user_check.sh [output-file]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-/tmp/social_task07/second_user.txt}"
mkdir -p "$(dirname "$OUT")"
exec > >(tee "$OUT") 2>&1
PY="$ROOT/.venv/bin/python"
W="$(mktemp -d /var/tmp/sa-friend.XXXX)"
trap 'rm -rf "$W"' EXIT
say() { printf '\n== %s\n' "$1"; }
refs() { git --git-dir="$1" for-each-ref --format='%(refname) %(objectname)'; }

say "1. The owner's repo (bare copy of main) and the friend's own empty content repo"
git clone -q --bare --single-branch -b main "$ROOT" "$W/upstream.git"
git init -q --bare -b main "$W/friend.git"
BEFORE="$(refs "$W/upstream.git")"
echo "  owner's repo main: $(git --git-dir="$W/upstream.git" rev-parse --short main)"

say "2. The friend clones it with his own HOME (no git name/email configured)"
export HOME="$W/home"; mkdir -p "$HOME"
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
git clone -q "$W/upstream.git" "$HOME/social-automation"
F="$HOME/social-automation"
printf 'DASHBOARD_PASSWORD=friend-pass-1\n' > "$F/.env"; chmod 600 "$F/.env"
printf '[github]\ncontent_remote = "%s"\n' "$W/friend.git" > "$F/config.local.toml"
echo "  git identity of the friend: '$(git config --global user.email || true)' (none)"

say "3. He publishes a reel; then something tries to push content to the owner's repo"
cd "$F"
"$PY" - "$W" <<'EOF'
import sys
from pathlib import Path
w = Path(sys.argv[1])
sys.path.insert(0, ".")
from socialauto.config import load_settings
from socialauto.content_repo import ContentPushRefused, ContentRepo
s = load_settings(root=Path(".").resolve())
v, c = w / "v.mp4", w / "c.png"
v.write_bytes(b"friend video"); c.write_bytes(b"friend cover")
repo = ContentRepo(s)
res = repo.publish("2026-11-12-suv-tejash", {"2026-11-12-suv-tejash.mp4": v, "2026-11-12-suv-tejash_cover.png": c}, "Suv tejash")
print(f"  published: committed={res.committed} pushed={res.pushed} folder={res.folder} note='{res.note}'")
for url in ("git@github.com:Abdurahman0/social-automation.git", str(w / "upstream.git"), "https://github.com/abdurahman0/Social-Automation"):
    try:
        repo.guard(url); print("  NOT REFUSED:", url); sys.exit(1)
    except ContentPushRefused:
        print("  refused content push to the owner's repo:", url if "github" in url else "upstream.git (origin)")
EOF
echo "  friend's content repo now has: $(git --git-dir="$W/friend.git" ls-tree -r --name-only main | grep reels/ | tr '\n' ' ')"
echo "  content commit author: $(git --git-dir="$W/friend.git" log -1 --format='%an <%ae>' main)"
echo "  code folder status (must be clean): '$(git -C "$F" status --porcelain)'"

say "4. The owner pushes an update; the friend updates (fast-forward only) and keeps his data"
git clone -q "$W/upstream.git" "$W/owner-work"
git -C "$W/owner-work" -c user.name=Owner -c user.email=o@e commit -q --allow-empty -m "Owner: new version"
git -C "$W/owner-work" push -q origin main
OWNER_AFTER="$(refs "$W/upstream.git")"
ENV_SUM="$(sha256sum "$F/.env" "$F/config.local.toml" | sha256sum)"
"$PY" - <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, ".")
from socialauto.updater import Updater
u = Updater(Path(".").resolve(), min_fetch_seconds=0)
st = u.status()
print(f"  update available: {st['available']} ({st.get('behind')} commit: {st['commits'][0]['title'] if st['commits'] else ''})")
print("  apply:", u.apply())
EOF
[ "$ENV_SUM" = "$(sha256sum "$F/.env" "$F/config.local.toml" | sha256sum)" ] && echo "  .env and config.local.toml unchanged: yes"
echo "  friend's content repo still there: $(git -C "$F/data/content-repo" log --oneline | wc -l) commits"

say "5. The owner's repo was never written by the friend"
AFTER="$(refs "$W/upstream.git")"
[ "$AFTER" = "$OWNER_AFTER" ] && echo "  owner's repo refs = only the owner's own push: yes"
[ "$(echo "$BEFORE" | wc -l)" = "$(echo "$AFTER" | wc -l)" ] && echo "  no new branches in the owner's repo: yes"
git --git-dir="$W/upstream.git" log --format='  %s' main | head -3
if git --git-dir="$W/upstream.git" ls-tree -r --name-only main | grep -q '^reels/'; then echo "  FAIL: reels in the owner's repo"; exit 1; fi
echo "  no reels/ in the owner's repo: yes"
echo
echo "Done."
