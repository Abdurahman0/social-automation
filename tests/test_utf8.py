"""Task 11: every text I/O is UTF-8, whatever the computer's locale (Korean Windows uses cp949 and crashed on 'ç').

1. A lint-style AST scan of `socialauto/` and `scripts/`: no text-mode open / read_text / write_text / subprocess
   text=True / log FileHandler / text tempfile without an explicit `encoding=` (subprocess also needs `errors=`).
2. The real ClaudeClient subprocess path with a prompt full of non-cp949 characters while Python believes the locale
   is cp949, using a fake `claude` binary.
3. The program entry switches the console to UTF-8 and the Windows launchers run Python in UTF-8 mode.
4. A reel stuck «To'xtab qoldi» by this error is retried by the existing «Qayta urinish» button.
"""

from __future__ import annotations

import ast
import asyncio
import io
import locale
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCANNED = [ROOT / "socialauto", ROOT / "scripts"]

NASTY = "Açaí — 한국어 텍스트 — oʻzbekcha gʻalla, Oʻzbekiston — 🚰💧 — naïve façade ½ €"

_SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}
_FILE_HANDLERS = {"FileHandler", "RotatingFileHandler", "TimedRotatingFileHandler", "WatchedFileHandler"}
_TEMPFILES = {"NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"}
# `.open()` on these returns binary/non-text objects (images, wav, archives, the browser) - never a text stream.
_BINARY_OPENERS = {"Image", "wave", "tarfile", "zipfile", "gzip", "webbrowser", "sf", "soundfile", "av"}


def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _has_kwargs_splat(call: ast.Call) -> bool:
    return any(k.arg is None for k in call.keywords)


def _const_str(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_true(node) -> bool:
    return node is not None and not (isinstance(node, ast.Constant) and not node.value)


def _text_mode(mode_node) -> bool:
    """True unless the mode is a literal containing 'b'."""
    mode = _const_str(mode_node)
    return mode is None or "b" not in mode


def _receiver(func: ast.Attribute) -> str:
    v = func.value
    if isinstance(v, ast.Name):
        return v.id
    if isinstance(v, ast.Attribute):
        return v.attr
    return ""


def utf8_problems(source: str, filename: str = "<src>") -> list[str]:
    """Every text-mode I/O call in `source` that does not name its encoding."""
    tree = ast.parse(source, filename)
    subprocess_names = {a.asname or a.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                        and node.module == "subprocess" for a in node.names if a.name in _SUBPROCESS_FUNCS}
    out: list[str] = []

    def bad(node, what):
        out.append(f"{filename}:{node.lineno}: {what}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _has_kwargs_splat(node):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        recv = _receiver(f) if isinstance(f, ast.Attribute) else ""
        has_enc = _kw(node, "encoding") is not None
        # builtin open / io.open / codecs.open / os.fdopen
        if (isinstance(f, ast.Name) and name == "open") or (recv in {"io", "codecs"} and name == "open") \
                or (recv == "os" and name == "fdopen"):
            mode = _kw(node, "mode") or (node.args[1] if len(node.args) > 1 else ast.Constant("r"))
            if _text_mode(mode) and not has_enc and len(node.args) < 4:
                bad(node, "open() in text mode without encoding=")
        # Path.open(mode)
        elif isinstance(f, ast.Attribute) and name == "open" and recv not in _BINARY_OPENERS | {"os"}:
            mode = _kw(node, "mode") or (node.args[0] if node.args else ast.Constant("r"))
            if _text_mode(mode) and not has_enc and len(node.args) < 3:
                bad(node, f"{recv}.open() in text mode without encoding=")
        elif isinstance(f, ast.Attribute) and name == "read_text":
            if not has_enc and not node.args:
                bad(node, "read_text() without encoding=")
        elif isinstance(f, ast.Attribute) and name == "write_text":
            if not has_enc and len(node.args) < 2:
                bad(node, "write_text() without encoding=")
        elif (recv == "subprocess" and name in _SUBPROCESS_FUNCS) or (isinstance(f, ast.Name) and name in subprocess_names):
            textual = _is_true(_kw(node, "text")) or _is_true(_kw(node, "universal_newlines")) or has_enc
            if textual and not (has_enc and _kw(node, "errors") is not None):
                bad(node, f"subprocess.{name}() in text mode without encoding= and errors=")
        elif name in _FILE_HANDLERS:
            if not has_enc:
                bad(node, f"{name}() without encoding=")
        elif name in _TEMPFILES:
            mode = _kw(node, "mode") or (node.args[0] if node.args else ast.Constant("w+b"))
            if _text_mode(mode) and not has_enc:
                bad(node, f"{name}() in text mode without encoding=")
        elif name == "TextIOWrapper":
            if not has_enc:
                bad(node, "TextIOWrapper() without encoding=")
    return out


def _files():
    for base in SCANNED:
        yield from sorted(base.rglob("*.py"))


# --- 1. the lint ----------------------------------------------------------------------------------------------------

def test_every_text_io_names_utf8():
    problems = []
    for path in _files():
        problems += utf8_problems(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
    assert not problems, "text I/O without an explicit encoding (cp949 crash on Korean Windows):\n" + "\n".join(problems)


def test_the_lint_catches_the_original_bug():
    """The exact line that crashed on the owner's PC, and its relatives, are all caught; the fixed forms pass."""
    src = """
import subprocess
from subprocess import run as r
subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=1)
subprocess.Popen(a, stdout=subprocess.PIPE, universal_newlines=True)
r(a, text=True)
open(p)
open(p, "w")
p.open("a")
p.read_text()
p.write_text("x")
RotatingFileHandler(p)
tempfile.NamedTemporaryFile("w")
subprocess.run(cmd, text=True, encoding="utf-8")
"""
    assert len(utf8_problems(src)) == 11
    ok = """
import subprocess
subprocess.run(cmd, input=prompt, text=True, encoding="utf-8", errors="replace")
subprocess.run(cmd, capture_output=True)
open(p, "rb"); open(p, "w", encoding="utf-8"); p.open("rb"); Image.open(p); wave.open(str(p), "rb")
p.read_text(encoding="utf-8"); p.write_text("x", encoding="utf-8"); p.read_bytes()
RotatingFileHandler(p, encoding="utf-8"); tempfile.NamedTemporaryFile(); tempfile.NamedTemporaryFile("w", encoding="utf-8")
"""
    assert utf8_problems(ok) == []


# --- 2. the Claude subprocess path under a cp949 locale -------------------------------------------------------------

FAKE_CLAUDE = r'''#!{python}
import json, os, sys
data = sys.stdin.buffer.read()
prompt = data.decode("utf-8")                        # strict: a mangled prompt fails here
with open(os.environ["FAKE_CLAUDE_LOG"], "wb") as f:
    f.write(data)
env = {{k: os.environ.get(k, "") for k in ("PYTHONUTF8", "PYTHONIOENCODING")}}
reply = {{"type": "result", "subtype": "success", "is_error": False,
          "structured_output": {{"echo": prompt, "env": env}}, "result": ""}}
sys.stdout.buffer.write(json.dumps(reply, ensure_ascii=False).encode("utf-8"))
'''


@pytest.fixture
def fake_claude_bin(tmp_path):
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(FAKE_CLAUDE.format(python=sys.executable), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def _cp949_locale(monkeypatch):
    """Simulate Korean Windows: every encoding Python would pick by default is cp949."""
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "cp949")
    monkeypatch.setattr(locale, "getencoding", lambda: "cp949", raising=False)
    monkeypatch.setattr(io, "text_encoding", lambda encoding, stacklevel=2: encoding or "cp949")
    monkeypatch.setenv("PYTHONIOENCODING", "cp949")
    monkeypatch.delenv("PYTHONUTF8", raising=False)


def test_simulation_really_breaks_the_old_code(monkeypatch, tmp_path):
    """Proof the simulation is real: the pre-Task-11 call (text=True, no encoding) fails exactly like on the PC."""
    _cp949_locale(monkeypatch)
    with pytest.raises(UnicodeEncodeError, match="cp949"):
        subprocess.run([sys.executable, "-c", "import sys; sys.stdin.buffer.read()"], input=NASTY,
                       capture_output=True, text=True, timeout=60, check=False)


def test_claude_client_sends_and_reads_utf8_under_cp949(monkeypatch, tmp_path, fake_claude_bin):
    """The exact call that crashed («Mavzu qidirish»): the prompt with 'ç', Korean, oʻ/gʻ and emoji reaches the CLI
    as UTF-8 bytes and the UTF-8 answer is read back intact, although Python believes the locale is cp949."""
    import socialauto.claude_client as cc
    from socialauto.config import ClaudeConfig
    _cp949_locale(monkeypatch)
    log = tmp_path / "prompt.bin"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setattr(cc, "_ENV_ALLOWED_PREFIXES", cc._ENV_ALLOWED_PREFIXES + ("FAKE_",))
    cfg = ClaudeConfig(binary=str(fake_claude_bin), config_dir=tmp_path / "claude-home", effort="",
                       timeout_seconds=60, min_interval_seconds=0)
    client = cc.ClaudeClient(cfg, tmp_path / "work")
    schema = {"type": "object", "properties": {"echo": {"type": "string"}, "env": {"type": "object"}}}
    data = client.generate_json("research-topics", NASTY, schema, system_prompt="Tizim: " + NASTY)
    assert data["echo"] == NASTY                                # arrived intact and came back intact
    assert log.read_bytes().decode("utf-8") == NASTY
    assert data["env"] == {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


FAKE_CLAUDE_ARGV = r'''#!{python}
import json, os, sys
sys.stdin.buffer.read()
argv = sys.argv[1:]
path = argv[argv.index("--system-prompt-file") + 1]
with open(path, "rb") as f:
    system = f.read().decode("utf-8")
reply = {{"type": "result", "subtype": "success", "is_error": False,
          "structured_output": {{"argv_chars": sum(len(a) + 1 for a in sys.argv), "system": system,
                                 "inline": "--system-prompt" in argv}}, "result": ""}}
sys.stdout.buffer.write(json.dumps(reply, ensure_ascii=False).encode("utf-8"))
'''


def test_long_system_prompt_never_goes_on_the_command_line(tmp_path):
    """«The command line is too long» on Windows: the brand rules made the system prompt longer than cmd.exe allows
    (8191 characters). The system prompt now travels in a UTF-8 file, so the command line stays short."""
    import socialauto.claude_client as cc
    from socialauto.config import ClaudeConfig
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(FAKE_CLAUDE_ARGV.format(python=sys.executable), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    cfg = ClaudeConfig(binary=str(exe), config_dir=tmp_path / "claude-home", effort="", timeout_seconds=60,
                       min_interval_seconds=0)
    work = tmp_path / "work"
    client = cc.ClaudeClient(cfg, work)
    system = ("Brend qoidalari: " + NASTY + "\n") * 2000
    schema = {"type": "object", "properties": {"argv_chars": {"type": "integer"}}}
    data = client.generate_json("research-topics", "mavzu", schema, system_prompt=system)
    assert data["system"] == system
    assert data["inline"] is False
    assert data["argv_chars"] < 8191
    assert list(work.iterdir()) == []


def test_child_env_forces_utf8(tmp_path, monkeypatch):
    from socialauto.claude_client import child_env
    monkeypatch.setenv("PYTHONIOENCODING", "cp949")
    env = child_env(tmp_path)
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"


# --- 3. program entry and Windows launchers -------------------------------------------------------------------------

def test_console_is_reconfigured_to_utf8(monkeypatch):
    from socialauto import utf8
    raw_out, raw_err = io.BytesIO(), io.BytesIO()
    out = io.TextIOWrapper(raw_out, encoding="cp949", errors="strict")
    err = io.TextIOWrapper(raw_err, encoding="cp949", errors="strict")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    utf8.setup_console()
    print(NASTY)
    print(NASTY, file=sys.stderr)
    sys.stdout.flush(); sys.stderr.flush()
    assert raw_out.getvalue().decode("utf-8").strip() == NASTY
    assert raw_err.getvalue().decode("utf-8").strip() == NASTY


def test_console_setup_survives_streams_without_reconfigure(monkeypatch):
    from socialauto import utf8
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    utf8.setup_console()                       # pythonw.exe has no console: must not crash


def test_windows_reexecs_in_utf8_mode(monkeypatch):
    from socialauto import utf8
    calls = []
    monkeypatch.setattr(utf8.sys, "platform", "win32")
    monkeypatch.setattr(utf8, "_utf8_mode", lambda: False)
    monkeypatch.delenv("SOCIALAUTO_UTF8_REEXEC", raising=False)
    monkeypatch.setattr(utf8.subprocess, "call", lambda cmd, env=None: calls.append((cmd, env)) or 0)
    monkeypatch.setattr(utf8.sys, "argv", ["C:\\sa\\socialauto\\__main__.py", "run"])
    with pytest.raises(SystemExit) as exit_info:
        utf8.ensure_utf8_mode()
    assert exit_info.value.code == 0
    cmd, env = calls[0]
    assert cmd[:4] == [sys.executable, "-X", "utf8", "-m"] and cmd[4:] == ["socialauto", "run"]
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8" and env["SOCIALAUTO_UTF8_REEXEC"] == "1"


def test_no_reexec_when_already_utf8_or_not_windows(monkeypatch):
    from socialauto import utf8
    monkeypatch.setattr(utf8.subprocess, "call", lambda *a, **k: pytest.fail("must not re-exec"))
    monkeypatch.setattr(utf8.sys, "platform", "linux")
    utf8.ensure_utf8_mode()
    monkeypatch.setattr(utf8.sys, "platform", "win32")
    monkeypatch.setattr(utf8, "_utf8_mode", lambda: True)
    utf8.ensure_utf8_mode()
    monkeypatch.setattr(utf8, "_utf8_mode", lambda: False)
    monkeypatch.setenv("SOCIALAUTO_UTF8_REEXEC", "1")      # loop guard
    utf8.ensure_utf8_mode()


def test_main_entry_calls_the_utf8_setup():
    src = (ROOT / "socialauto" / "__main__.py").read_text(encoding="utf-8")
    assert "ensure_utf8_mode()" in src and "setup_console()" in src


def test_windows_launchers_run_python_in_utf8_mode():
    for name in ("install.ps1", "scripts/windows_service.ps1"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "PYTHONUTF8" in text and "PYTHONIOENCODING" in text, name
        assert "-X utf8" in text or "'-X', 'utf8'" in text, name


def test_cli_prints_uzbek_under_cp949_child(tmp_path):
    """A real child Python with a cp949 console: the CLI's own output must not crash."""
    env = {**os.environ, "PYTHONIOENCODING": "cp949"}
    env.pop("PYTHONUTF8", None)
    code = ("import sys; sys.path.insert(0, %r); from socialauto import utf8; utf8.setup_console(); print(%r)"
            % (str(ROOT), NASTY))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env, timeout=60)
    assert res.returncode == 0, res.stderr.decode("utf-8", "replace")
    assert res.stdout.decode("utf-8").strip() == NASTY


# --- 4. a reel stuck by the cp949 error is retried by the existing button ------------------------------------------

def test_cp949_stuck_research_is_retried_by_the_button(app, clock, fake_claude, monkeypatch):
    """Before the fix the research failed 5 times with the cp949 error and the reel stayed «To'xtab qoldi».
    After the update the owner presses the existing «🔄 Qayta urinish»: the research runs again with the same idea
    (with its 'ç' and Korean letters intact) and the reel moves on to topic approval. Nothing is posted."""
    from conftest import dryrun_entries, run_all_jobs
    from socialauto.store import FAILED, RESEARCHING, TOPIC_PENDING
    from socialauto.telegram_bot import TelegramBot
    wf = app.workflow
    idea = "Açaí va suv — 한국 tajribasi, oʻgʻit 💧"
    vid = wf.request_new(idea)

    def old_bug(*a, **k):        # what subprocess.run(text=True) without encoding raised on the owner's PC
        raise UnicodeEncodeError("cp949", "\xe7", 720, 721, "illegal multibyte sequence")
    monkeypatch.setattr(wf.reel_writer, "research", old_bug)
    for _ in range(8):
        run_all_jobs(app)
        clock.advance(hours=2)
    v = app.store.video(vid)
    assert v["status"] == FAILED and "cp949" in v["last_error"]
    give_up = [i for i in app.outbox.pending(300) if i.kind == "error" and i.payload.get("buttons")]
    assert len(give_up) == 1 and "«Mavzu qidirish» to'xtatildi" in give_up[0].payload["text"]
    retry = give_up[0].payload["buttons"][0][0]
    assert retry[0] == "🔄 Qayta urinish"

    monkeypatch.undo()                                          # the fixed code is installed (update + restart)
    fake_claude.calls.clear()
    ok, msg = asyncio.run(TelegramBot(app).handle_button(111, retry[1]))
    assert ok and "Qayta urinyapman" in msg
    assert app.store.video(vid)["status"] == RESEARCHING
    assert run_all_jobs(app) == ["research"]
    assert app.store.video(vid)["status"] == TOPIC_PENDING      # waits for the owner's Approve again (law 3)
    assert any(idea in prompt for task, prompt in fake_claude.calls if task.startswith("research"))
    assert dryrun_entries(app) == []                            # nothing posted or queued automatically
