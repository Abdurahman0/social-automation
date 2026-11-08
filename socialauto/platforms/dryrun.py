"""Dry-run record (law 4): every "post" in dry-run mode is appended to data/dryrun_posts.json instead of going to
a platform. The file is the proof of what would have been posted (platform, title, caption, files, time)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()


class DryRunLog:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def append(self, entry: dict[str, Any]) -> None:
        with _lock:
            items = self.read()
            items.append({"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)

    def find(self, platform: str, marker: str) -> dict[str, Any] | None:
        return next((e for e in self.read() if e.get("platform") == platform and e.get("marker") == marker), None)
