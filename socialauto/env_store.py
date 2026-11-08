"""The local `.env` file: read, update and mask values for the Setup ("Sozlash") page.

Secrets stay on this computer (law 7): the file is written atomically and made readable only by the current user
(chmod 600 on Linux/macOS; on Windows the inherited permissions are removed and only the current user gets access).
Values are never logged and never returned in full — only masked ("12••••••89").
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

KEYS = ("DASHBOARD_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_IDS", "BUFFER_API_KEY", "META_APP_ID",
        "META_APP_SECRET", "PEXELS_API_KEY", "PIXABAY_API_KEY")
SECRET_KEYS = {"DASHBOARD_PASSWORD", "TELEGRAM_BOT_TOKEN", "BUFFER_API_KEY", "META_APP_SECRET", "PEXELS_API_KEY",
               "PIXABAY_API_KEY"}
_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*)$")


def read(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _LINE.match(line)
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            out[m.group(1)] = v
    return out


def clean_value(value: str) -> str:
    """One line, no surrounding spaces or quotes (a value cannot break the file)."""
    v = (value or "").replace("\r", "").replace("\n", "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def write(path: Path, updates: dict[str, str], template: Path | None = None) -> None:
    """Set keys (keeping comments and other lines). Empty string = clear the value."""
    for k in updates:
        if k not in KEYS:
            raise KeyError(k)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else (
        template.read_text(encoding="utf-8").splitlines() if template and template.exists() else [])
    done = set()
    for i, line in enumerate(lines):
        m = _LINE.match(line)
        if m and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={clean_value(updates[m.group(1)])}"
            done.add(m.group(1))
    for k, v in updates.items():
        if k not in done:
            lines.append(f"{k}={clean_value(v)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    protect(tmp)
    os.replace(tmp, path)
    protect(path)


def protect(path: Path) -> None:
    """Only the current user may read the file."""
    if sys.platform.startswith("win"):
        user = os.environ.get("USERNAME", "")
        if user:
            subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                           capture_output=True, check=False)
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "••••••"
    return f"{value[:2]}{'•' * 6}{value[-2:]}"


def public_view(values: dict[str, str]) -> dict[str, dict]:
    """What the Setup page may see: whether each key is set, and a masked (or, for ids, plain) value."""
    out = {}
    for k in KEYS:
        v = values.get(k, "")
        out[k] = {"set": bool(v), "shown": (v if k in ("TELEGRAM_ALLOWED_USER_IDS", "META_APP_ID") else mask(v))
                  if k != "DASHBOARD_PASSWORD" else ("••••••" if v else "")}
    return out
