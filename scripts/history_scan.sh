#!/usr/bin/env bash
# Scan EVERY commit of a branch before it is public: secrets (gitleaks), personal paths, media (reels / voice /
# video), proof/ and reels/ folders, and the removed posting code. Exit 1 if anything is found.
#   scripts/history_scan.sh [branch] [gitleaks-binary]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
BR="${1:-main}"
GL="${2:-$(command -v gitleaks || echo "$ROOT/bin/tools/glx/usr/bin/gitleaks")}"
bad=0
echo "== branch $BR: $(git rev-list --count "$BR") commits, newest $(git rev-parse --short "$BR")"

echo; echo "== 1. secrets (gitleaks over every commit)"
if "$GL" git --no-banner --no-color --log-opts="$BR" . >/tmp/sa-gitleaks.txt 2>&1; then tail -n 3 /tmp/sa-gitleaks.txt
else tail -n 3 /tmp/sa-gitleaks.txt; bad=1; fi

echo; echo "== 2. personal paths / the local user name in any commit (author metadata excluded)"
user="$(id -un)"
n=$(git log -p "$BR" | grep -v '^Author:' | grep -i -c -E "/home/$user|/Users/$user|C:\\\\Users\\\\$user|$user" || true)
echo "   matches: $n"; [ "$n" = 0 ] || bad=1

echo; echo "== 3. media files in any commit (only synthetic test voices are allowed: tests/fixtures/sample_voice_*.wav)"
media=$(git log --name-only --format= "$BR" | sort -u | grep -i -E '\.(mp4|mov|webm|mkv|wav|mp3|m4a|ogg|aac|flac)$' || true)
echo "${media:-   none}" | sed 's/^/   /'
if echo "$media" | grep -v -E '^(tests/fixtures/sample_voice_[a-z_]+\.wav)?$' | grep -q .; then bad=1; fi

echo; echo "== 4. reels/ and proof/ in any commit"
r=$(git log --name-only --format= "$BR" | grep -c -E '^reels/' || true)
p=$(git log --name-only --format= "$BR" | grep -c -E '^proof/' || true)
echo "   reels/: $r   proof/: $p"; [ "$r" = 0 ] && [ "$p" = 0 ] || bad=1

echo; echo "== 5. posting / upload code in any commit (application code; docs and the guard test only name it)"
# The names are split so this file itself never matches the guard test (tests/test_guards.py).
PAT='videos\(\)\s*\.\s*ins''ert|media''_publish|post''_now\(|publish''_direct|\bPub''lisher\b|youtube\.up''load|MediaFile''Upload'
hits=$(for c in $(git rev-list "$BR"); do
  git grep -I -l -E "$PAT" \
    "$c" -- 'socialauto/*.py' 'socialauto/**/*.py' 'scripts/*' 'remotion/src/*' 2>/dev/null
done | sed 's/^[0-9a-f]*://' | grep -v '^scripts/history_scan.sh$' | sort -u)
echo "${hits:-   none}" | sed 's/^/   /'; [ -z "$hits" ] || bad=1

echo; if [ "$bad" = 0 ]; then echo "RESULT: clean — safe to publish"; else echo "RESULT: NOT clean"; fi
exit "$bad"
