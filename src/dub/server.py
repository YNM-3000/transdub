"""Auto-start / auto-stop the local GPT-SoVITS api_v2 server for cloning dubs.

Discovers the install via env (or sensible defaults), starts the server when
it's down, waits for it to load, and stops it on close — but only if *we*
started it (an already-running server is left alone).

Config (all optional):
  GPT_SOVITS_URL        server url (default http://127.0.0.1:9880)
  GPT_SOVITS_HOME       repo dir (default ~/Development/GPT-SoVITS)
  GPT_SOVITS_CONDA_ENV  conda env name (default gsv)
  GPT_SOVITS_PYTHON     explicit python interpreter for the server
  GPT_SOVITS_LAUNCH     full launch command override (run in HOME)
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from .gptsovits_backend import DEFAULT_URL, reachable

log = logging.getLogger("recreator.dub")

DEFAULT_HOME = "~/Development/GPT-SoVITS"
READY_TIMEOUT_S = 180.0
_LOG_FILE = os.path.join(tempfile.gettempdir(), "recreator-gptsovits.log")


def _home() -> Path:
    return Path(os.path.expanduser(os.environ.get("GPT_SOVITS_HOME", DEFAULT_HOME)))


def _conda_base() -> str | None:
    for candidate in (shutil.which("conda"), "/opt/homebrew/Caskroom/miniforge/base/bin/conda"):
        if candidate and Path(candidate).exists():
            try:
                out = subprocess.run(
                    [candidate, "info", "--base"], capture_output=True, text=True, timeout=10
                )
                if out.returncode == 0 and out.stdout.strip():
                    return out.stdout.strip()
            except Exception:
                pass
    return None


def _python() -> str | None:
    explicit = os.environ.get("GPT_SOVITS_PYTHON")
    if explicit and Path(explicit).is_file():
        return explicit
    base = _conda_base()
    if base:
        env = os.environ.get("GPT_SOVITS_CONDA_ENV", "gsv")
        py = Path(base) / "envs" / env / "bin" / "python"
        if py.is_file():
            return str(py)
    return None


def is_installed() -> bool:
    """True if we can launch the server (repo + a usable interpreter present)."""
    if os.environ.get("GPT_SOVITS_LAUNCH"):
        return (_home() / "api_v2.py").is_file()
    return (_home() / "api_v2.py").is_file() and _python() is not None


def _launch(url: str) -> subprocess.Popen:
    parsed = urlparse(url)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 9880
    override = os.environ.get("GPT_SOVITS_LAUNCH")
    cmd = shlex.split(override) if override else [_python(), "api_v2.py", "-a", host, "-p", str(port)]
    log.info("dub: starting GPT-SoVITS server (%s) …", " ".join(cmd))
    logf = open(_LOG_FILE, "w")
    return subprocess.Popen(cmd, cwd=str(_home()), stdout=logf, stderr=subprocess.STDOUT)


def _wait_ready(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if reachable(url):
            return True
        time.sleep(2)
    return False


class VoiceServer:
    """Ensure a GPT-SoVITS server is up; stop it on close only if we started it."""

    def __init__(self, url: str | None = None, autostart: bool = True) -> None:
        self.url = (url or os.environ.get("GPT_SOVITS_URL", DEFAULT_URL)).rstrip("/")
        self.autostart = autostart
        self._proc: subprocess.Popen | None = None

    def ensure(self) -> bool:
        """Return True if the server is available, starting it if needed/possible."""
        if reachable(self.url):
            return True
        if not self.autostart or not is_installed():
            return False
        self._proc = _launch(self.url)
        if _wait_ready(self.url, READY_TIMEOUT_S):
            log.info("dub: GPT-SoVITS server ready")
            return True
        log.warning("dub: GPT-SoVITS server did not become ready (see %s)", _LOG_FILE)
        self.close()
        return False

    def close(self) -> None:
        if self._proc is not None:
            log.info("dub: stopping GPT-SoVITS server")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except Exception:
                self._proc.kill()
            self._proc = None

    def __enter__(self) -> "VoiceServer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
