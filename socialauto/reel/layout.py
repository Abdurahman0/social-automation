"""Where text goes on the 1080x1920 reel, and the Instagram UI safe-zone check.

Instagram (and YouTube Shorts) draw their own UI over a reel: the caption, audio line and profile at the bottom, the
like/comment/share column at the right. Nothing of ours may sit in the bottom ~20 % or at the right edge. The boxes
below are passed to Remotion as they are, so the check measures exactly what is drawn. Subtitles sit at eye level
(a little below the middle), the title at the top.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

W, H = 1080, 1920
BOTTOM_UNSAFE = 0.20         # bottom 20 %
RIGHT_UNSAFE = 150           # the reel's action buttons column (px from the right edge)
TOP_UNSAFE = 110             # status bar / "Reels" header
LEFT_MARGIN = 64


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


def default_layout() -> dict[str, Box]:
    usable_w = W - LEFT_MARGIN - RIGHT_UNSAFE - 10
    return {"title": Box(LEFT_MARGIN, 150, usable_w, 230),
            "info": Box(LEFT_MARGIN, 560, usable_w, 380),
            "subtitle": Box(LEFT_MARGIN, 1060, usable_w, 280)}


def safe_zone_problems(layout: dict[str, Box]) -> list[str]:
    out = []
    limit_y = int(H * (1 - BOTTOM_UNSAFE))
    for name, b in layout.items():
        if b.bottom > limit_y:
            out.append(f"{name} reaches y={b.bottom}px, into the bottom {int(BOTTOM_UNSAFE * 100)}% (max {limit_y}px)")
        if b.right > W - RIGHT_UNSAFE:
            out.append(f"{name} reaches x={b.right}px, under the right-side buttons (max {W - RIGHT_UNSAFE}px)")
        if b.y < TOP_UNSAFE or b.x < 24:
            out.append(f"{name} starts too close to the top/left edge")
    sub = layout.get("subtitle")
    if sub and not (0.45 * H <= sub.y + sub.h / 2 <= 0.68 * H):
        out.append("subtitles are not at eye level (their centre must be between 45% and 68% of the height)")
    return out


def text_fit_problems(text: str, box: Box, font_px: int, max_lines: int, char_w: float = 0.62) -> list[str]:
    """A rough check that a text fits its box at the given size (Montserrat ExtraBold ~0.62 em per character)."""
    per_line = max(1, int(box.w / (font_px * char_w)))
    lines, cur = 1, 0
    for word in text.split():
        add = len(word) + (1 if cur else 0)
        if cur + add > per_line:
            lines, cur = lines + 1, len(word)
        else:
            cur += add
    if lines > max_lines:
        return [f"\"{text[:40]}…\" needs {lines} lines in a box for {max_lines}"]
    return []


def as_props(layout: dict[str, Box]) -> dict:
    return {k: asdict(v) for k, v in layout.items()}
