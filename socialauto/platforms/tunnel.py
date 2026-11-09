"""Temporary public links for Buffer (Buffer fetches the reel's video / the story's cover from a public URL).

A tiny local HTTP server serves ONLY the files registered for one post, each under a random unguessable path, and a
free Cloudflare quick tunnel (`cloudflared tunnel --url http://127.0.0.1:<port>`, no account, random
*.trycloudflare.com address) makes it reachable. When the post is published (or fails) the files are unregistered,
the tunnel process is stopped and the server shut down: the link is gone.
"""

from __future__ import annotations

import logging
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import requests

log = logging.getLogger(__name__)

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
MIME = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
DOWNLOAD_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"


class TunnelError(RuntimeError):
    pass


class FileServer:
    """Serves registered files only (GET/HEAD, byte ranges), on 127.0.0.1."""

    def __init__(self):
        self.files: dict[str, Path] = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):      # quiet: the paths are secret-ish
                log.debug("tunnel file server: " + fmt, *args)

            def _send(self, head_only: bool):
                path = outer.files.get(self.path.split("?", 1)[0])
                if not path or not path.exists():
                    self.send_error(404)
                    return
                size = path.stat().st_size
                start, end = 0, size - 1
                rng = self.headers.get("Range")
                m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
                if m and (m.group(1) or m.group(2)):
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else size - 1
                    else:
                        start = max(0, size - int(m.group(2)))
                    end = min(end, size - 1)
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                else:
                    self.send_response(200)
                self.send_header("Content-Type", MIME.get(path.suffix.lower(), "application/octet-stream"))
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                if head_only:
                    return
                with open(path, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = f.read(min(1 << 16, left))
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        left -= len(chunk)

            def do_GET(self):
                self._send(False)

            def do_HEAD(self):
                self._send(True)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> "FileServer":
        self.thread.start()
        return self

    def add(self, path: Path) -> str:
        key = f"/{secrets.token_urlsafe(24)}/{path.name}"
        self.files[key] = path
        return key

    def stop(self) -> None:
        self.files.clear()
        self.httpd.shutdown()
        self.httpd.server_close()


def cloudflared_binary(root: Path) -> str:
    local = root / "bin" / ("cloudflared.exe" if sys.platform.startswith("win") else "cloudflared")
    if local.exists():
        return str(local)
    found = shutil.which("cloudflared")
    if not found:
        raise TunnelError("cloudflared is not installed: run the installer again (install.sh / install.ps1)")
    return found


@contextmanager
def public_files(files: list[Path], binary: str, start_timeout: float = 60.0) -> Iterator[list[str]]:
    """Public https URLs for these files while the block runs; everything is torn down afterwards."""
    server = FileServer().start()
    proc = None
    try:
        keys = [server.add(p) for p in files]
        proc = subprocess.Popen([binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{server.port}"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        base, lines = None, []
        deadline = time.monotonic() + start_timeout
        while time.monotonic() < deadline and proc.poll() is None:
            line = proc.stdout.readline()
            lines.append(line)
            m = URL_RE.search(line)
            if m:
                base = m.group(0)
                break
        if not base:
            raise TunnelError("the Cloudflare quick tunnel did not start: " + "".join(lines[-5:])[-300:])
        threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()   # keep the pipe drained
        urls = [base + k for k in keys]
        for _ in range(30):                     # DNS for a new trycloudflare host can take a few seconds
            try:
                if requests.head(urls[0], timeout=10).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(2)
        else:
            raise TunnelError("the public link did not become reachable")
        yield urls
    finally:
        server.files.clear()
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        server.stop()


def make_public_files(root: Path):
    def factory(files: list[Path]):
        return public_files(files, cloudflared_binary(root))
    return factory
