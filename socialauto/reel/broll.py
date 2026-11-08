"""Real B-roll (video first, then photos) from free sources whose licences allow reuse. No cartoons, 3D or AI images.

Providers (in config order, each skipped when it needs a key that is not set):
- Wikimedia Commons — no key. Only files whose licence is CC0 / Public domain / CC BY / CC BY-SA are used (NC and
  ND licences are refused: they forbid commercial use or editing). Author and licence are recorded for attribution.
- Pexels — free API key (PEXELS_API_KEY). Pexels licence: free use, no attribution required (credited anyway).
- Pixabay — free API key (PIXABAY_API_KEY). Pixabay content licence: free use, no attribution required.
Not used: Mixkit (no API; automated downloading is not allowed by its terms as far as published), UzA (photos need
permission). Every clip's source and licence go to `<work>/broll/sources.json` and SOURCES.md.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import requests

log = logging.getLogger(__name__)

USER_AGENT = "SocialAutomationReels/1.0 (personal non-bulk tool; https://www.mediawiki.org/wiki/API:Etiquette) python-requests"
ALLOWED = re.compile(r"^(cc0|public domain|pd|cc by(-sa)?( \d\.\d)?( [a-z]+)?|cc-by(-sa)?-\d\.\d|attribution)", re.I)
REFUSED = re.compile(r"\b(nc|nd|non-?commercial|no ?deriv|fair use|all rights reserved)\b", re.I)
MAX_BYTES = 80_000_000
AI_WORDS = re.compile(r"\b(ai[- ]generated|midjourney|stable diffusion|dall-?e|render(ed)?|3d|cartoon|illustration|"
                      r"clipart|vector|animation|animated|drawing|diagram|logo|map|how does|explained|infographic|cgi)\b", re.I)


class BrollError(RuntimeError):
    pass


@dataclass
class Clip:
    part: str
    kind: str                # video | image
    file: str                # path relative to the work folder ("broll/03-body1.mp4")
    provider: str
    title: str
    author: str
    license: str
    source_url: str
    seconds: float | None = None
    query: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Candidate:
    kind: str
    url: str
    provider: str
    title: str
    author: str
    license: str
    source_url: str
    width: int = 0
    height: int = 0
    seconds: float | None = None
    size: int | None = None
    extra: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def search(self, query: str, kind: str, limit: int = 8) -> list[Candidate]: ...


def license_ok(name: str) -> bool:
    n = (name or "").strip()
    return bool(n) and not REFUSED.search(n) and bool(ALLOWED.search(n))


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


class Commons:
    name = "Wikimedia Commons"
    API = "https://commons.wikimedia.org/w/api.php"

    def __init__(self, session: requests.Session | None = None):
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT

    def search(self, query: str, kind: str, limit: int = 8) -> list[Candidate]:
        ftype = "filetype:video" if kind == "video" else "filetype:bitmap"
        params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                  "gsrsearch": f"{ftype} {query}", "gsrlimit": limit, "prop": "imageinfo",
                  "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1080}
        r = self.s.get(self.API, params=params, timeout=30)
        r.raise_for_status()
        out = []
        for page in (r.json().get("query", {}).get("pages") or {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            lic = _strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
            mime = info.get("mime", "")
            if kind == "video" and not mime.startswith("video/"):
                continue
            if kind == "image" and mime not in ("image/jpeg", "image/png"):
                continue
            url = info.get("url") if kind == "video" else (info.get("thumburl") or info.get("url"))
            url = (url or "").split("?", 1)[0] or None              # drop tracking parameters
            alt = None
            if kind == "video" and url and (info.get("height") or 0) > 1080 and "/commons/" in url:
                # Commons keeps 720p transcodes: much lighter to download and decode than a 4K original
                head, name = url.rsplit("/", 1)
                alt = head.replace("/commons/", "/commons/transcoded/") + f"/{name}/{name}.720p.vp9.webm"
            out.append(Candidate(kind, url, self.name, page.get("title", "").replace("File:", ""),
                                 _strip_html((meta.get("Artist") or {}).get("value", "")) or "Wikimedia Commons",
                                 lic, info.get("descriptionurl", ""), info.get("width", 0), info.get("height", 0),
                                 float(info["duration"]) if info.get("duration") else None, info.get("size"),
                                 {"alt_url": alt} if alt else {}))
        return out


class Pexels:
    name = "Pexels"

    def __init__(self, key: str, session: requests.Session | None = None):
        self.key = key
        self.s = session or requests.Session()

    def search(self, query: str, kind: str, limit: int = 8) -> list[Candidate]:
        url = "https://api.pexels.com/videos/search" if kind == "video" else "https://api.pexels.com/v1/search"
        r = self.s.get(url, params={"query": query, "orientation": "portrait", "per_page": limit},
                       headers={"Authorization": self.key}, timeout=30)
        r.raise_for_status()
        out = []
        if kind == "video":
            for v in r.json().get("videos", []):
                files = sorted([f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"
                                and (f.get("height") or 0) <= 1920], key=lambda f: -(f.get("height") or 0))
                if files:
                    out.append(Candidate("video", files[0]["link"], self.name, f"Pexels video {v['id']}",
                                         (v.get("user") or {}).get("name", "Pexels"), "Pexels License", v.get("url", ""),
                                         files[0].get("width", 0), files[0].get("height", 0), v.get("duration")))
        else:
            for p in r.json().get("photos", []):
                out.append(Candidate("image", p["src"]["large2x"], self.name, p.get("alt") or f"Pexels photo {p['id']}",
                                     p.get("photographer", "Pexels"), "Pexels License", p.get("url", ""),
                                     p.get("width", 0), p.get("height", 0)))
        return out


class Pixabay:
    name = "Pixabay"

    def __init__(self, key: str, session: requests.Session | None = None):
        self.key = key
        self.s = session or requests.Session()

    def search(self, query: str, kind: str, limit: int = 8) -> list[Candidate]:
        if kind == "video":
            r = self.s.get("https://pixabay.com/api/videos/", params={"key": self.key, "q": query, "per_page": max(3, limit),
                                                                     "safesearch": "true"}, timeout=30)
            r.raise_for_status()
            out = []
            for v in r.json().get("hits", []):
                f = (v.get("videos") or {}).get("large") or (v.get("videos") or {}).get("medium") or {}
                if f.get("url"):
                    out.append(Candidate("video", f["url"], self.name, v.get("tags", "Pixabay video"), v.get("user", "Pixabay"),
                                         "Pixabay Content License", v.get("pageURL", ""), f.get("width", 0),
                                         f.get("height", 0), v.get("duration")))
            return out
        r = self.s.get("https://pixabay.com/api/", params={"key": self.key, "q": query, "image_type": "photo",
                                                           "orientation": "vertical", "per_page": max(3, limit),
                                                           "safesearch": "true"}, timeout=30)
        r.raise_for_status()
        return [Candidate("image", h["largeImageURL"], self.name, h.get("tags", "Pixabay photo"), h.get("user", "Pixabay"),
                          "Pixabay Content License", h.get("pageURL", ""), h.get("imageWidth", 0), h.get("imageHeight", 0))
                for h in r.json().get("hits", [])]


def make_providers(order: tuple[str, ...], pexels_key: str = "", pixabay_key: str = "",
                   session: requests.Session | None = None) -> list[Provider]:
    out: list[Provider] = []
    for name in order:
        if name == "pexels" and pexels_key:
            out.append(Pexels(pexels_key, session))
        elif name == "pixabay" and pixabay_key:
            out.append(Pixabay(pixabay_key, session))
        elif name == "commons":
            out.append(Commons(session))
    return out


def acceptable(c: Candidate, used: set[str]) -> bool:
    if c.url in used or not c.url:
        return False
    if not license_ok(c.license) and c.provider == Commons.name:
        return False
    if AI_WORDS.search(c.title or ""):
        return False                       # no illustrations, renders, maps or AI images
    if c.size and c.size > MAX_BYTES and not c.extra.get("alt_url"):
        return False
    if c.kind == "video" and c.seconds is not None and c.seconds < 3:
        return False
    if c.width and c.height and min(c.width, c.height) < 480:
        return False
    return True


def relevance(c: Candidate, query: str) -> float:
    """Share of the query's words that appear in the clip's title (0..1)."""
    want = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2}
    have = set(re.findall(r"[a-z]+", (c.title or "").lower()))
    have |= {w[:-1] for w in have if w.endswith("s")}
    return len(want & have) / len(want) if want else 0.0


def score(c: Candidate, query: str = "") -> float:
    s = 3.0 * relevance(c, query) if query else 0.0
    s += 2.0 if c.kind == "video" else 0.0
    if c.width and c.height:
        s += 1.0 if c.height >= c.width else 0.3            # portrait fits 9:16 best
        s += min(1.0, min(c.width, c.height) / 1080)
    return s


def download(url: str, dest: Path, session: requests.Session) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with session.get(url, stream=True, timeout=120, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        size = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise BrollError("file too large")
                f.write(chunk)
    tmp.replace(dest)
    return dest


def simplify(query: str) -> list[str]:
    """Fallback queries: the full phrase, then shorter ones ("water treatment plant aerial" -> "water treatment")."""
    words = query.split()
    out = [query]
    for n in (3, 2, 1):
        if len(words) > n:
            out.append(" ".join(words[:n]))
    return list(dict.fromkeys(out)) + ["water", "river water"]


def collect(parts: list[dict], workdir: Path, providers: list[Provider], session: requests.Session | None = None,
            pause: float = 0.5) -> list[Clip]:
    """One clip per script part. Raises BrollError if a part gets nothing (never a fake or AI image)."""
    s = session or requests.Session()
    clips: list[Clip] = []
    used: set[str] = set()
    for i, part in enumerate(parts, start=1):
        chosen = None
        for query in simplify(part.get("broll") or "water"):
            for kind in ("video", "image"):
                cands = []
                for p in providers:
                    try:
                        cands += p.search(query, kind)
                    except Exception as exc:     # noqa: BLE001 - one provider down: try the others
                        log.warning("B-roll search failed at %s: %s", p.name, exc)
                    time.sleep(pause)
                cands = [c for c in cands if acceptable(c, used)]
                if any(relevance(c, query) > 0 for c in cands):          # on-topic clips only, when there are any
                    cands = [c for c in cands if relevance(c, query) > 0]
                cands = sorted(cands, key=lambda c: score(c, query), reverse=True)
                for c in cands[:3]:
                    ext = ".mp4" if c.kind == "video" and ".webm" not in c.url else (".webm" if c.kind == "video" else ".jpg")
                    rel = f"broll/{i:02d}-{part['part']}{ext}"
                    try:
                        try:
                            download(c.extra.get("alt_url") or c.url, workdir / rel, s)
                        except Exception:         # noqa: BLE001 - no transcode: the original file
                            if not c.extra.get("alt_url"):
                                raise
                            download(c.url, workdir / rel, s)
                    except Exception as exc:      # noqa: BLE001
                        log.warning("B-roll download failed: %s", exc)
                        continue
                    chosen = Clip(part["part"], c.kind, rel, c.provider, c.title[:160], c.author[:120], c.license or "",
                                  c.source_url, c.seconds, query)
                    used.add(c.url)
                    break
                if chosen:
                    break
            if chosen:
                break
        if not chosen:
            raise BrollError(f"no licensed real footage found for part {part['part']} ({part.get('broll')})")
        clips.append(chosen)
    write_sources(workdir, clips)
    return clips


def write_sources(workdir: Path, clips: list[Clip]) -> None:
    d = workdir / "broll"
    d.mkdir(parents=True, exist_ok=True)
    (d / "sources.json").write_text(json.dumps([c.as_dict() for c in clips], indent=1, ensure_ascii=False), encoding="utf-8")
    lines = ["# B-roll manbalari", "", "| Qism | Turi | Manba | Muallif | Litsenziya | Havola |", "|---|---|---|---|---|---|"]
    for c in clips:
        lines.append(f"| {c.part} | {'video' if c.kind == 'video' else 'rasm'} | {c.provider} | {c.author} | {c.license} | "
                     f"{c.source_url} |")
    (workdir / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_sources(workdir: Path) -> list[Clip]:
    f = workdir / "broll" / "sources.json"
    if not f.exists():
        return []
    return [Clip(**c) for c in json.loads(f.read_text(encoding="utf-8"))]
