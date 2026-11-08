"""The "Ko'nikmalar" (Skills) section: the Claude skills installed for the account this project uses (account 1).

Read-only. Sources:
- personal skills: ~/.claude/skills/**/SKILL.md (synced folders included; the same skill synced several times is
  shown once);
- project skills: <repo>/.claude/skills/**/SKILL.md;
- plugin skills: every plugin in ~/.claude/plugins/installed_plugins.json -> <installPath>/skills/**/SKILL.md, plus
  <installPath>/commands/*.md shown as commands ("buyruq").
Only the frontmatter `name` and `description` are used. Folder names (UUIDs), paths and file contents never leave this
module. A broken SKILL.md is skipped and logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_SECONDS = 60
MAX_FILE_BYTES = 256_000
_cache: dict[str, tuple[float, dict]] = {}

# Words that read better with their usual capitalisation.
_WORDS = {"pdf": "PDF", "ux": "UX", "ui": "UI", "api": "API", "docx": "DOCX", "pptx": "PPTX", "xlsx": "XLSX",
          "github": "GitHub", "ai": "AI", "mcp": "MCP", "seo": "SEO", "csv": "CSV"}


@dataclass
class Skill:
    key: str
    name: str            # readable ("Caveman commit")
    slug: str            # the real name ("caveman-commit")
    invoke: str          # how to call it ("/caveman-commit", "/caveman:caveman-commit")
    short: str           # first sentence
    description: str     # the full description (plain text)
    group: str           # personal | project | plugin
    source: str          # friendly label ("Shaxsiy", "Loyiha", "Plagin: Caveman")
    kind: str            # skill | command
    synced: bool = False
    used: bool = False


def pretty_name(slug: str) -> str:
    """caveman-commit -> "Caveman commit"; google_workspace -> "Google workspace"; built-in-browser -> "Built-in browser"."""
    words = [w for w in re.split(r"[-_\s]+", slug.strip()) if w]
    if not words:
        return slug
    out = []
    for i, w in enumerate(words):
        low = w.lower()
        if low in _WORDS:
            out.append(_WORDS[low])
        else:
            out.append(low.capitalize() if i == 0 else low)
    name = " ".join(out)
    return name.replace("Built in", "Built-in").replace("built in", "built-in")


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """The `---` YAML header's simple keys (plain, quoted, and `>` / `|` block scalars). None if there is none."""
    if not text.startswith("---"):
        return None
    end = re.search(r"^---\s*$", text[3:], re.M)
    if not end:
        return None
    lines = text[3:3 + end.start()].splitlines()
    data: dict[str, str] = {}
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2).rstrip()
        if value in (">", "|", ">-", "|-", ">+", "|+") or value == "":
            block = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            joiner = "\n" if value.startswith("|") else " "
            data[key] = joiner.join(b for b in block).strip() if value else " ".join(b for b in block if b).strip()
            continue
        data[key] = _unquote(value)
        i += 1
    return data


def first_sentence(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    s = m.group(1) if m else text
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return s


def _read(path: Path) -> dict[str, str] | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("too large")
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        if not meta or not meta.get("name") or not meta.get("description"):
            raise ValueError("no name/description in the frontmatter")
        if not re.fullmatch(r"[A-Za-z0-9][\w.:-]{0,80}", meta["name"]):
            raise ValueError("unusual name")
        return meta
    except Exception as exc:       # noqa: BLE001 - a broken skill is skipped quietly
        log.info("Skill skipped (%s): %s", exc, path.parent.name[:40])
        return None


def _key(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def _skill(meta: dict[str, str], group: str, source: str, invoke_prefix: str = "", kind: str = "skill",
           synced: bool = False) -> Skill:
    slug = meta["name"]
    desc = " ".join(meta["description"].split())
    return Skill(_key(group, source, kind, slug), pretty_name(slug), slug, f"/{invoke_prefix}{slug}",
                 first_sentence(desc), desc, group, source, kind, synced)


def plugin_label(plugin_id: str) -> str:
    return "Plagin: " + pretty_name(plugin_id.split("@", 1)[0])


def scan(claude_dir: Path, project_dir: Path, used: set[str] | None = None) -> dict:
    used = used or set()
    skills: list[Skill] = []
    seen: set[tuple[str, str, str]] = set()

    def add(s: Skill) -> None:
        ident = (s.group, s.source, s.kind + ":" + s.slug)
        if ident in seen:
            return
        seen.add(ident)
        s.used = s.slug in used
        skills.append(s)

    personal = claude_dir / "skills"
    if personal.is_dir():
        for path in sorted(personal.rglob("SKILL.md")):
            meta = _read(path)
            if meta:
                add(_skill(meta, "personal", "Shaxsiy", synced="synced" in path.relative_to(personal).parts))
    project = project_dir / ".claude" / "skills"
    if project.is_dir():
        for path in sorted(project.rglob("SKILL.md")):
            meta = _read(path)
            if meta:
                add(_skill(meta, "project", "Loyiha"))
    try:
        installed = json.loads((claude_dir / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        plugins = installed.get("plugins", installed) if isinstance(installed, dict) else {}
    except Exception as exc:        # noqa: BLE001
        if (claude_dir / "plugins" / "installed_plugins.json").exists():
            log.info("installed_plugins.json not readable: %s", exc)
        plugins = {}
    for plugin_id, entries in plugins.items():
        entries = entries if isinstance(entries, list) else [entries]
        for entry in entries:
            root = Path(str((entry or {}).get("installPath", "")))
            if not root.is_dir():
                continue
            label, prefix = plugin_label(plugin_id), plugin_id.split("@", 1)[0] + ":"
            for path in sorted((root / "skills").rglob("SKILL.md")) if (root / "skills").is_dir() else []:
                meta = _read(path)
                if meta:
                    add(_skill(meta, "plugin", label, prefix))
            commands = root / "commands"
            for path in sorted(commands.glob("*.md")) if commands.is_dir() else []:
                meta = _read_command(path)
                if meta:
                    add(_skill(meta, "plugin", label, prefix, kind="command"))
    order = {"personal": 0, "project": 1, "plugin": 2}
    skills.sort(key=lambda s: (order[s.group], s.source, s.kind != "skill", s.name.lower()))
    groups: dict[str, dict] = {}
    for s in skills:
        g = groups.setdefault(s.source, {"label": s.source, "group": s.group, "count": 0})
        g["count"] += 1
    return {"skills": [asdict(s) for s in skills], "groups": list(groups.values()), "total": len(skills),
            "used_count": sum(s.used for s in skills)}


def _read_command(path: Path) -> dict[str, str] | None:
    """A plugin command (commands/<name>.md): the name is the file name; the description from its frontmatter."""
    try:
        meta = parse_frontmatter(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:       # noqa: BLE001
        log.info("Command skipped (%s): %s", exc, path.name)
        return None
    if not meta.get("description"):
        log.info("Command skipped (no description): %s", path.name)
        return None
    return {"name": meta.get("name") or path.stem, "description": meta["description"]}


def pipeline_skills() -> tuple[set[str], str]:
    """Which skills the bot's own Claude calls use, decided from the client's command line: with --safe-mode no
    skills, plugins or hooks load at all."""
    from ..claude_client import ClaudeClient
    from ..config import ClaudeConfig
    cmd = ClaudeClient(ClaudeConfig(), Path("."))._base_command()
    if "--safe-mode" in cmd:
        return set(), ("hech qaysi ko'nikma ishlatilmaydi. Claude chaqiruvlari xavfsiz rejimda "
                       "(--safe-mode) ishlaydi, ko'nikma va plaginlar yuklanmaydi. Bu ataylab qilingan — bot har safar "
                       "bir xil, oldindan aytib bo'ladigan tarzda ishlaydi.")
    return set(), "ko'nikmalar aniqlanmadi."


def cached_scan(claude_dir: Path, project_dir: Path) -> dict:
    key = f"{claude_dir}|{project_dir}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    used, note = pipeline_skills()
    data = scan(claude_dir, project_dir, used)
    data["used_note"] = note
    _cache[key] = (now, data)
    return data
