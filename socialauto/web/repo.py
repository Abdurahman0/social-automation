"""The "GitHub" section: what the next push would send, in plain words. Read-only.

Only read-only git commands are run (remote, rev-parse, rev-list, log, status, reflog, check-ignore); the website
never fetches or pushes. Remote URLs are reduced to "owner/name" (credentials and hosts never leave this module).
`.env` and `secrets/` are never read; secret-looking paths are filtered out of every list even if git showed them.
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

TASHKENT = ZoneInfo("Asia/Tashkent")
SAFE_COMMANDS = {"remote", "rev-parse", "rev-list", "log", "status", "reflog", "for-each-ref"}
SECRET_RE = re.compile(r"(^|/)(\.env(?!\.example$)(\..*)?|secrets?/.*|.*client_secret.*|.*token.*\.json|.*\.pem|.*\.key|"
                       r".*credentials.*\.json|.*\.session)$", re.I)
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]
CATEGORIES = ["Kod", "Sayt", "Hujjatlar", "Testlar", "Sozlamalar", "Media/rasmlar", "Boshqa"]
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp4", ".mov", ".wav", ".mp3", ".ogg", ".m4a",
             ".ttf", ".otf", ".woff", ".woff2", ".ico"}

# What .gitignore keeps on this computer, in words. A group is shown when any of its patterns is in .gitignore.
NEVER_GROUPS = [
    ("Parollar, tokenlar va ruxsat fayllari", "Telegram bot tokeni, sayt paroli, YouTube va Instagram ruxsatlari.",
     ("env", "secret", "token", ".pem", ".key", "credential", "session")),
    ("Ma'lumotlar bazasi va sizning ovoz yozuvlaringiz", "Bot bazasi, siz yuborgan ovozlar va tayyorlangan videolar.",
     ("/data/", "*.db")),
    ("Jurnal (log) fayllari", "Botning ish jurnali faqat shu kompyuterda qoladi.", ("/logs/",)),
    ("Render va sinov chiqishlari", "Oraliq render fayllari va vaqtinchalik sinov papkalari.", ("/work/", "*.wav")),
    ("Katta model fayllari", "Nutqni tanish va sinov ovozi modellari — kerak bo'lsa qayta yuklab olinadi.",
     ("/models/", "*.onnx")),
    ("Musiqa fayllari", "Siz qo'shgan musiqa fayllari (litsenziyalari har xil).", ("assets/music",)),
    ("Dasturiy kutubxonalar va yuklab olingan dasturlar", "Python muhiti va cloudflared — qayta o'rnatiladi.",
     (".venv", "/bin/", "__pycache__", "node_modules")),
]


class Git:
    def __init__(self, root: Path):
        self.root = root

    def run(self, *args: str, check: bool = False) -> str:
        if args[0] not in SAFE_COMMANDS:
            raise ValueError(f"git {args[0]} is not a read-only command")
        try:
            out = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, timeout=20,
                                 check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("git %s failed: %s", args[0], exc)
            return ""
        if out.returncode != 0:
            if check:
                raise RuntimeError(out.stderr.strip()[:200])
            return ""
        return out.stdout


def repo_name(url: str) -> str | None:
    """"https://user:token@github.com/owner/name.git" / "git@github.com:owner/name.git" -> "owner/name"."""
    url = url.strip()
    m = re.search(r"[:/]([^/:@\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def host_of(url: str) -> str:
    m = re.search(r"(?:@|//)(?:[^@/]*@)?([^/:]+)", url)
    host = (m.group(1) if m else "").lower()
    return "GitHub" if host.endswith("github.com") else (host or "git")


def is_secret(path: str) -> bool:
    return bool(SECRET_RE.search(path))


def category(path: str) -> str:
    p = path.lower()
    ext = Path(p).suffix
    if p.startswith("tests/"):
        return "Testlar" if ext not in MEDIA_EXT else "Media/rasmlar"
    if ext in MEDIA_EXT:
        return "Media/rasmlar"
    if p.startswith("socialauto/web/static/"):
        return "Sayt"
    if ext in (".md", ".txt") or p.startswith(("docs/", "proof/")) or p in ("license", "notice"):
        return "Hujjatlar"
    if (ext in (".toml", ".ini", ".cfg", ".service", ".json", ".yml", ".yaml") or p.startswith("systemd/")
            or Path(p).name in (".gitignore", ".env.example") or Path(p).name.startswith("requirements")):
        return "Sozlamalar"
    if ext in (".py", ".sh", ".js", ".css", ".html"):
        return "Kod"
    return "Boshqa"


def group_files(paths: list[str]) -> list[dict]:
    groups: dict[str, list[str]] = {}
    for p in paths:
        if is_secret(p):
            continue
        groups.setdefault(category(p), []).append(p)
    return [{"label": c, "count": len(groups[c]), "files": sorted(groups[c])} for c in CATEGORIES if c in groups]


def when(iso: str) -> str:
    """Tashkent time: "8-noyabr, 11:24"."""
    dt = datetime.fromisoformat(iso).astimezone(TASHKENT)
    return f"{dt.day}-{MONTHS[dt.month - 1]}, {dt:%H:%M}"


def clean_subject(subject: str) -> str:
    return re.sub(r"\s*Co-Authored-By:.*$", "", subject, flags=re.I).strip() or "(izohsiz o'zgarish)"


def commits(git: Git, rev_range: list[str], limit: int) -> list[dict]:
    raw = git.run("log", f"-n{limit}", "--name-only", "--format=%x1e%h%x1f%cI%x1f%s", *rev_range)
    out = []
    for block in raw.split("\x1e"):
        if not block.strip():
            continue
        head, _, files = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) != 3:
            continue
        short, iso, subject = parts
        paths = [f for f in files.splitlines() if f.strip()]
        out.append({"title": clean_subject(subject), "when": when(iso), "at": iso, "short": short,
                    "files": len([p for p in paths if not is_secret(p)]), "groups": group_files(paths)})
    return out


def never_pushed(root: Path) -> list[dict]:
    try:
        text = (root / ".gitignore").read_text(encoding="utf-8").lower()
    except OSError:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#") and not ln.startswith("!")]
    out = []
    for title, detail, needles in NEVER_GROUPS:
        if any(n.lower() in ln for ln in lines for n in needles):
            out.append({"title": title, "detail": detail})
    return out


def status(root: Path) -> dict:
    git = Git(root)
    if not git.run("rev-parse", "--is-inside-work-tree").strip():
        return {"is_repo": False}
    branch = git.run("rev-parse", "--abbrev-ref", "HEAD").strip() or "main"
    remotes = [ln.split() for ln in git.run("remote", "-v").splitlines() if ln.strip()]
    remote_url = next((r[1] for r in remotes if r[0] == "origin" and len(r) > 1),
                      remotes[0][1] if remotes and len(remotes[0]) > 1 else None)
    remote_name = next((r[0] for r in remotes if len(r) > 1 and r[1] == remote_url), None)
    upstream = git.run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip() if remote_url else ""
    if remote_url and not upstream and remote_name:
        candidate = f"{remote_name}/{branch}"
        if git.run("rev-parse", "--verify", "--quiet", f"refs/remotes/{candidate}").strip():
            upstream = candidate
    if upstream:
        ahead_range = [f"{upstream}..HEAD"]
    elif remote_url:
        ahead_range = ["HEAD", "--not", "--remotes"]
    else:
        ahead_range = ["HEAD"]                       # never pushed: everything goes with the first push
    ahead = int((git.run("rev-list", "--count", *ahead_range) or "0").strip() or 0)
    last_push = None
    if upstream:
        line = git.run("reflog", "show", "-n1", "--date=iso-strict", "--format=%gd", f"refs/remotes/{upstream}").strip()
        m = re.search(r"@\{(.+)\}", line)
        if m:
            try:
                last_push = when(m.group(1))
            except ValueError:
                last_push = None
    porcelain = git.run("status", "--porcelain=v1", "-z", "--untracked-files=all")
    changed = []
    entries = porcelain.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        if len(e) > 3:
            path = e[3:]
            if e[0] in "RC":                         # renames carry the old path as the next entry
                i += 1
            changed.append(path)
        i += 1
    total_commits = int((git.run("rev-list", "--count", "HEAD") or "0").strip() or 0)
    return {
        "is_repo": True,
        "connected": bool(remote_url),
        "repo": repo_name(remote_url) if remote_url else None,
        "host": host_of(remote_url) if remote_url else None,
        "branch": branch,
        "has_upstream": bool(upstream),
        "last_push": last_push,
        "ahead": ahead,
        "ahead_commits": commits(git, ahead_range, 30) if ahead else [],
        "uncommitted": {"count": len([p for p in changed if not is_secret(p)]), "groups": group_files(changed)},
        "never": never_pushed(root),
        "history": commits(git, ["HEAD"], 20),
        "total_commits": total_commits,
    }
