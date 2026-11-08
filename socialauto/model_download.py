"""Download the Uzbek speech model (rubaiSTT, int8 CTranslate2 build) from its official Hugging Face repository
into `models/`, with a progress bar, then verify every large file against the SHA-256 the repository publishes.
Re-running is cheap: files that are already complete and correct are not downloaded again."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO = "Mavlyudabegim/rubaistt-medium-int8-ct2"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_hashes(api, repo: str = REPO) -> dict[str, str]:
    """{file name: sha256} for the files stored with Git LFS (the model weights)."""
    info = api.model_info(repo, files_metadata=True)
    return {s.rfilename: s.lfs.sha256 for s in info.siblings if getattr(s, "lfs", None)}


def verify(target: Path, hashes: dict[str, str]) -> list[str]:
    """Names of files that are missing or do not match their published checksum."""
    return [name for name, digest in hashes.items()
            if not (target / name).exists() or sha256(target / name) != digest]


def download(target: Path, repo: str = REPO) -> int:
    from huggingface_hub import HfApi, snapshot_download
    api = HfApi()
    try:
        hashes = expected_hashes(api, repo)
    except Exception:                      # noqa: BLE001
        print("  ! Hugging Face'ga ulanib bo'lmadi / could not reach Hugging Face. Internetni tekshirib qayta urinib ko'ring.")
        return 1
    if hashes and (target / "model.bin").exists() and not verify(target, hashes):
        print("  ✓ Nutq modeli allaqachon yuklangan va tekshirilgan / speech model already downloaded and verified")
        return 0
    print(f"  ↓ Nutq modeli yuklanmoqda / downloading the speech model ({repo}) …")
    try:
        snapshot_download(repo, local_dir=str(target))
    except Exception:                      # noqa: BLE001
        print("  ! Yuklab bo'lmadi / download failed. Internetni tekshirib, o'rnatuvchini qayta ishga tushiring.")
        return 1
    bad = verify(target, hashes)
    if bad:
        for name in bad:
            (target / name).unlink(missing_ok=True)
        print("  ! Fayl buzilgan (checksum mos emas) / checksum mismatch: " + ", ".join(bad)
              + ". O'rnatuvchini qayta ishga tushiring / run the installer again.")
        return 1
    print("  ✓ Nutq modeli tayyor, checksum to'g'ri / speech model ready, checksum OK")
    return 0


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    sys.exit(download(root / "models" / REPO.split("/")[1]))
