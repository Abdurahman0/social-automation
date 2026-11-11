"""Task 11: UTF-8 everywhere, whatever the computer's locale.

On Windows Python uses the locale code page (cp949 on Korean Windows, cp1251 on Russian, ...) for every text I/O
that does not name an encoding. Every such call in this package names UTF-8 (guard: tests/test_utf8.py); this
module is the belt and braces at the program entry:

* `ensure_utf8_mode()` re-runs `python -m socialauto ...` once with `-X utf8` on Windows when UTF-8 mode is off,
  so even third-party libraries that open text files without an encoding read and write UTF-8.
* `setup_console()` switches stdout/stderr to UTF-8 (errors replaced), so console logging and `print` never crash.
"""

from __future__ import annotations

import os
import subprocess
import sys

REEXEC_FLAG = "SOCIALAUTO_UTF8_REEXEC"      # loop guard: the child never re-executes again


def _utf8_mode() -> bool:
    return bool(sys.flags.utf8_mode)


def utf8_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def ensure_utf8_mode() -> None:
    """On Windows without UTF-8 mode: run this same command again as `python -X utf8 -m socialauto ...` and exit
    with its code. Elsewhere (Linux/macOS locales are UTF-8) or when already in UTF-8 mode: do nothing."""
    if sys.platform != "win32" or _utf8_mode() or os.environ.get(REEXEC_FLAG) == "1":
        return
    env = utf8_env()
    env[REEXEC_FLAG] = "1"
    cmd = [sys.executable, "-X", "utf8", "-m", "socialauto", *sys.argv[1:]]
    try:
        code = subprocess.call(cmd, env=env)
    except KeyboardInterrupt:
        code = 130
    except OSError:
        return                                   # could not re-run: carry on; every own I/O names UTF-8 anyway
    raise SystemExit(code)


def setup_console() -> None:
    """stdout/stderr in UTF-8 with replacement, so a log line with 'ç' or Korean never raises UnicodeEncodeError."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:                  # pythonw.exe (no console) or a replaced stream
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):            # a stream that was already written to in an odd way
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
