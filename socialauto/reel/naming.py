"""Date-based naming (owner's rule): everything is named by the PUBLISH date, `YYYY-MM-DD-topic`.

    work/<date>-<topic>/                 the reel's work folder (B-roll, voice, props, frames, report)
    exports/<date>-<topic>_vN.mp4        every render gets a new N; an old version is never overwritten
    research/<date>-<topic>.md           the research file
    reels/<date>-<topic>/                in the git repo (video, cover, research, script, sources)

When the publish date changes, `rename_all` moves every one of them to the new date (and the caller updates the
Buffer draft titles).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
                ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                 "u", "f", "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o", "q", "g", "h"]))
VERSION_RE = re.compile(r"_v(\d+)\.mp4$")


def slugify(text: str, max_words: int = 6) -> str:
    """"Toshkentda suv yo'qotilishi 40%" -> "toshkentda-suv-yoqotilishi-40"."""
    t = "".join(_CYR.get(c, c) for c in text.lower())
    t = t.replace("o‘", "o").replace("g‘", "g").replace("o'", "o").replace("g'", "g").replace("ʻ", "").replace("’", "")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", t)
    return "-".join(words[:max_words]) or "reel"


def base_name(publish: date, topic_slug: str) -> str:
    return f"{publish.isoformat()}-{topic_slug}"


@dataclass(frozen=True)
class Places:
    work_base: Path          # work/
    exports: Path            # exports/
    research: Path           # research/
    reels: Path              # <repo>/reels/

    def work(self, base: str) -> Path:
        return self.work_base / base

    def research_file(self, base: str) -> Path:
        return self.research / f"{base}.md"

    def reel_dir(self, base: str) -> Path:
        return self.reels / base

    def versions(self, base: str) -> list[Path]:
        if not self.exports.is_dir():
            return []
        out = [p for p in self.exports.glob(f"{base}_v*.mp4") if VERSION_RE.search(p.name)]
        return sorted(out, key=lambda p: int(VERSION_RE.search(p.name).group(1)))

    def next_export(self, base: str) -> tuple[int, Path]:
        """The next free `_vN` (never reuses a number, even if a file was deleted, thanks to the marker file)."""
        self.exports.mkdir(parents=True, exist_ok=True)
        used = [int(VERSION_RE.search(p.name).group(1)) for p in self.versions(base)]
        marker = self.work(base) / ".last_version"
        if marker.exists():
            try:
                used.append(int(marker.read_text().strip()))
            except ValueError:
                pass
        n = max(used, default=0) + 1
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(n))
        return n, self.exports / f"{base}_v{n}.mp4"


def _git_mv(repo: Path, src: Path, dst: Path) -> bool:
    """git mv when the folder is tracked (keeps history); False when it is not tracked."""
    tracked = subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", str(src)], capture_output=True)
    if tracked.returncode != 0:
        return False
    subprocess.run(["git", "-C", str(repo), "mv", str(src), str(dst)], check=True, capture_output=True)
    return True


def rename_all(places: Places, old: str, new: str, repo: Path | None = None) -> list[str]:
    """Move every file/folder of a reel from the old base name to the new one. Returns what was renamed."""
    if old == new:
        return []
    done = []
    src, dst = places.work(old), places.work(new)
    if src.exists():
        shutil.move(str(src), str(dst))
        done.append("work")
    for p in places.versions(old):
        target = p.with_name(p.name.replace(old, new, 1))
        p.rename(target)
        done.append(f"export {target.name}")
    rf = places.research_file(old)
    if rf.exists():
        rf.rename(places.research_file(new))
        done.append("research")
    rd = places.reel_dir(old)
    if rd.exists():
        if not (repo and _git_mv(repo, rd, places.reel_dir(new))):
            shutil.move(str(rd), str(places.reel_dir(new)))
        done.append("reels")
        for f in places.reel_dir(new).glob(f"{old}*"):          # files named after the base inside the folder
            f.rename(f.with_name(f.name.replace(old, new, 1)))
    return done
