import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone

import httpx
from PyQt6.QtCore import QThread, pyqtSignal


GITHUB_REPO = "DDFantasyV/PoeditCopilot"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
EXE_DOWNLOAD_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/PoeditCopilot.exe"
CHECKSUM_DOWNLOAD_URL = f"{EXE_DOWNLOAD_URL}.sha256"

APP_BASENAME = "PoeditCopilot"
CHECK_TIMEOUT_SECONDS = 10.0
DEFAULT_INTERVAL_HOURS = 24

DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, read=120.0)
DOWNLOAD_CHUNK_SIZE = 256 * 1024
STAGED_EXE_SUFFIX = ".new"
UPDATE_SCRIPT_NAME = "PoeditCopilot-update.ps1"
LEGACY_SCRIPT_NAME = "PoeditCopilot-update.bat"

CANCEL_MESSAGE = "Download cancelled."


class UpdateCheckError(Exception):
    """Raised when the latest release version cannot be determined."""


class UpdateDownloadError(Exception):
    """Raised when the update package cannot be downloaded or verified."""


def _version_from_exe_name():
    stem = os.path.splitext(os.path.basename(sys.executable or ""))[0]
    marker = stem.rfind("-")
    if marker == -1:
        return ""
    candidate = stem[marker + 1:]
    if candidate and all(part.isdigit() for part in candidate.split(".")):
        return candidate
    return ""


def _detect_version():
    try:
        from version import __version__ as version
        return str(version)
    except ImportError:
        # Frozen builds have no importable version module, so fall back to the
        # executable name: "PoeditCopilot-0.10.2.exe" -> "0.10.2".
        return _version_from_exe_name() or "0.0.0"


APP_VERSION = _detect_version()


def _pick_asset_url(assets, suffix):
    for asset in assets or []:
        name = str(asset.get("name") or "")
        url = asset.get("browser_download_url") or ""
        if name.lower().endswith(suffix) and url:
            return url
    return ""


class UpdateInfo:
    """Result of a successful update check."""

    def __init__(self, current_version, latest_version, release_url, published_at="", notes="", assets=None):
        self.current_version = current_version
        self.latest_version = latest_version
        self.release_url = release_url or RELEASES_PAGE
        self.published_at = published_at
        self.notes = notes
        self.assets = assets or []

    @property
    def version(self):
        return str(self.latest_version or "").strip().lstrip("vV")

    @property
    def exe_url(self):
        return _pick_asset_url(self.assets, ".exe") or EXE_DOWNLOAD_URL

    @property
    def checksum_url(self):
        return _pick_asset_url(self.assets, ".sha256") or CHECKSUM_DOWNLOAD_URL

    def __repr__(self):
        return (
            f"UpdateInfo(current_version={self.current_version!r}, "
            f"latest_version={self.latest_version!r})"
        )


def parse_version(text):
    """Convert a version string into a comparable tuple, or None if unparsable."""
    value = str(text or "").strip().lstrip("vV")
    if not value:
        return None

    # Drop pre-release / build metadata: "1.2.3-rc1" -> "1.2.3".
    for separator in ("+", "-"):
        value = value.split(separator, 1)[0]

    numbers = []
    for part in value.split("."):
        if not part.isdigit():
            return None
        numbers.append(int(part))
    if not numbers:
        return None

    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)


def is_newer_version(latest, current):
    """Return True only when both versions parse and ``latest`` is greater."""
    latest_tuple = parse_version(latest)
    current_tuple = parse_version(current)
    if latest_tuple is None or current_tuple is None:
        return False
    return latest_tuple > current_tuple


def utc_now():
    return datetime.now(timezone.utc)


def format_check_time(moment=None):
    return (moment or utc_now()).replace(microsecond=0).isoformat()


def parse_check_time(text):
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(str(text).strip())
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def is_check_due(last_check_text, interval_hours=DEFAULT_INTERVAL_HOURS, now=None):
    """Return True when enough time passed since the last recorded check."""
    try:
        interval_hours = float(interval_hours)
    except (TypeError, ValueError):
        interval_hours = DEFAULT_INTERVAL_HOURS
    if interval_hours <= 0:
        return True

    last_check = parse_check_time(last_check_text)
    if last_check is None:
        return True

    reference = now or utc_now()
    return (reference - last_check).total_seconds() >= interval_hours * 3600


def fetch_latest_release(current_version=APP_VERSION, timeout_seconds=CHECK_TIMEOUT_SECONDS):
    """Fetch the latest published release from the GitHub API."""
    headers = {
        "User-Agent": f"PoeditCopilot/{current_version}",
        "Accept": "application/vnd.github+json",
    }
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(LATEST_RELEASE_API, headers=headers)
    except httpx.HTTPError as error:
        raise UpdateCheckError(f"Network error: {error}") from error

    if response.status_code == 404:
        raise UpdateCheckError("No published release was found.")
    if response.status_code == 403:
        raise UpdateCheckError("GitHub API rate limit reached. Try again later.")
    if response.status_code >= 400:
        raise UpdateCheckError(f"GitHub returned HTTP {response.status_code}.")

    try:
        data = response.json()
    except ValueError as error:
        raise UpdateCheckError(f"Invalid release response: {error}") from error

    latest_version = str(data.get("tag_name") or data.get("name") or "").strip()
    if not latest_version:
        raise UpdateCheckError("The latest release has no version tag.")

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        release_url=data.get("html_url") or RELEASES_PAGE,
        published_at=data.get("published_at") or "",
        notes=data.get("body") or "",
        assets=data.get("assets") or [],
    )


class UpdateCheckWorker(QThread):
    """Background worker so the update check never blocks the UI."""

    check_finished = pyqtSignal(object)
    check_failed = pyqtSignal(str)

    def __init__(self, current_version=APP_VERSION, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self):
        try:
            info = fetch_latest_release(self.current_version)
        except UpdateCheckError as error:
            self.check_failed.emit(str(error))
            return
        except Exception as error:  # Never let the checker crash the app.
            self.check_failed.emit(f"Unexpected error: {error}")
            return
        self.check_finished.emit(info)


def is_frozen_app():
    """Return True when running from a frozen (PyInstaller) executable."""
    return bool(getattr(sys, "frozen", False))


def versioned_exe_name(version):
    cleaned = str(version or "").strip().lstrip("vV")
    return f"{APP_BASENAME}-{cleaned}.exe" if cleaned else f"{APP_BASENAME}.exe"


def is_versioned_exe_name(path):
    """True for ``PoeditCopilot-<version>.exe`` names produced by the updater."""
    stem = os.path.splitext(os.path.basename(str(path)))[0]
    prefix = APP_BASENAME + "-"
    if not stem.startswith(prefix):
        return False
    return parse_version(stem[len(prefix):]) is not None


def target_exe_path(install_dir, version):
    return os.path.join(install_dir, versioned_exe_name(version))


def staged_exe_path(install_dir, version):
    return target_exe_path(install_dir, version) + STAGED_EXE_SUFFIX


def final_path_from_staged(staged_path):
    if not str(staged_path).endswith(STAGED_EXE_SUFFIX):
        raise ValueError(f"Staged path must end with {STAGED_EXE_SUFFIX!r}: {staged_path}")
    return str(staged_path)[: -len(STAGED_EXE_SUFFIX)]


def find_staged_update(install_dir, current_version):
    """Return ``(version, staged_path)`` for the newest staged build, else None."""
    if not os.path.isdir(install_dir):
        return None

    newest = None
    suffix = ".exe" + STAGED_EXE_SUFFIX
    for entry in os.listdir(install_dir):
        if not entry.lower().endswith(suffix):
            continue
        stem = entry[: -len(suffix)]
        marker = stem.rfind("-")
        if marker == -1:
            continue
        version = stem[marker + 1:]
        if parse_version(version) is None:
            continue
        if not is_newer_version(version, current_version):
            continue
        path = os.path.join(install_dir, entry)
        try:
            if os.path.getsize(path) <= 0:
                continue
        except OSError:
            continue
        if newest is None or parse_version(version) > parse_version(newest[0]):
            newest = (version, path)
    return newest


def read_checksum_file(text):
    """Extract the first SHA256 hex digest from a checksum file's contents."""
    for token in str(text or "").split():
        candidate = token.strip().lower()
        if len(candidate) == 64 and all(char in "0123456789abcdef" for char in candidate):
            return candidate
    return ""


def fetch_expected_checksum(checksum_url, timeout_seconds=CHECK_TIMEOUT_SECONDS):
    """Fetch the published SHA256 digest for the release asset, or "" when absent."""
    if not checksum_url:
        return ""
    headers = {"User-Agent": "PoeditCopilot-updater", "Accept": "text/plain,*/*"}
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(checksum_url, headers=headers)
    except httpx.HTTPError:
        return ""
    if response.status_code >= 400:
        return ""
    return read_checksum_file(response.text)


def compute_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _quote_ps(value):
    """Wrap a value as a PowerShell single-quoted literal."""
    return "'" + str(value).replace("'", "''") + "'"


def stage_update_download(
    download_url,
    staged_path,
    checksum_url="",
    expected_sha256="",
    progress_callback=None,
    cancel_check=None,
):
    """Download a release asset to ``staged_path`` (a ``<name>.exe.new`` path).

    Streams to a temporary ``.part`` file, verifies the checksum when one is
    available, then atomically renames it into place. Raises
    ``UpdateDownloadError`` on failure or cancellation and returns ``staged_path``.
    """
    staged_path = os.path.abspath(staged_path)
    part_path = staged_path + ".part"
    directory = os.path.dirname(staged_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

    if not expected_sha256 and checksum_url:
        expected_sha256 = fetch_expected_checksum(checksum_url)

    if progress_callback is not None:
        progress_callback(0, 0)

    bytes_written = 0
    try:
        with httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            with client.stream("GET", download_url) as response:
                if response.status_code >= 400:
                    raise UpdateDownloadError(f"Download failed with HTTP {response.status_code}.")
                total = int(response.headers.get("Content-Length") or 0)
                with open(part_path, "wb") as handle:
                    for chunk in response.iter_bytes(DOWNLOAD_CHUNK_SIZE):
                        if cancel_check is not None and cancel_check():
                            raise UpdateDownloadError(CANCEL_MESSAGE)
                        if not chunk:
                            continue
                        handle.write(chunk)
                        bytes_written += len(chunk)
                        if progress_callback is not None:
                            progress_callback(bytes_written, total)
    except UpdateDownloadError:
        _safe_remove(part_path)
        raise
    except httpx.HTTPError as error:
        _safe_remove(part_path)
        raise UpdateDownloadError(f"Network error: {error}") from error
    except OSError as error:
        _safe_remove(part_path)
        raise UpdateDownloadError(f"Could not write the update file: {error}") from error

    if bytes_written <= 0:
        _safe_remove(part_path)
        raise UpdateDownloadError("The downloaded update file is empty.")

    if expected_sha256 and compute_sha256(part_path).lower() != expected_sha256.lower():
        _safe_remove(part_path)
        raise UpdateDownloadError("The downloaded file failed its checksum check.")

    try:
        os.replace(part_path, staged_path)
    except OSError as error:
        _safe_remove(part_path)
        raise UpdateDownloadError(f"Could not finalize the update file: {error}") from error

    return staged_path


class UpdateDownloadWorker(QThread):
    """Background worker that downloads the latest build next to the current one."""

    progress = pyqtSignal(int, int)
    download_finished = pyqtSignal(str)
    download_failed = pyqtSignal(str)

    def __init__(self, download_url, staged_path, checksum_url="", expected_sha256="", parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.staged_path = staged_path
        self.checksum_url = checksum_url
        self.expected_sha256 = expected_sha256
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            staged_path = stage_update_download(
                self.download_url,
                self.staged_path,
                checksum_url=self.checksum_url,
                expected_sha256=self.expected_sha256,
                progress_callback=lambda done, total: self.progress.emit(done, total),
                cancel_check=lambda: self._cancelled,
            )
        except UpdateDownloadError as error:
            self.download_failed.emit(str(error))
            return
        except Exception as error:  # Never let the downloader crash the app.
            self.download_failed.emit(f"Unexpected error: {error}")
            return
        self.download_finished.emit(staged_path)


def write_swap_script(staged_path, old_exe_path="", log_path=""):
    """Write a PowerShell helper that waits for this process to exit, swaps the EXE, then restarts it.

    A PowerShell script is used instead of a self-deleting batch file: ``cmd.exe``
    re-reads a running ``.bat`` from disk, so ``del "%~f0"`` inside a batch spawns
    extra shells and loops forever.  PowerShell reads its script up front, so the
    helper can safely delete itself without running twice.
    """
    staged_path = os.path.abspath(staged_path)
    new_exe_path = final_path_from_staged(staged_path)
    script_path = os.path.join(os.path.dirname(new_exe_path), UPDATE_SCRIPT_NAME)
    # Drop the helper written by older builds, which could loop forever.
    _safe_remove(os.path.join(os.path.dirname(new_exe_path), LEGACY_SCRIPT_NAME))
    pid = os.getpid()

    lines = ["$ErrorActionPreference = 'SilentlyContinue'"]
    if log_path:
        lines.append(
            "$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); "
            f'"[$stamp] applying update to {os.path.basename(new_exe_path)}" | '
            f"Add-Content -LiteralPath {_quote_ps(log_path)} -Encoding UTF8"
        )
    lines.extend(
        [
            "$deadline = (Get-Date).AddMinutes(10)",
            f"while ((Get-Process -Id {pid} -ErrorAction SilentlyContinue) -and "
            "((Get-Date) -lt $deadline)) { Start-Sleep -Milliseconds 500 }",
            f"$moved = $false",
            "while (-not $moved -and ((Get-Date) -lt $deadline)) {",
            f"    Move-Item -LiteralPath {_quote_ps(staged_path)} "
            f"-Destination {_quote_ps(new_exe_path)} -Force -ErrorAction SilentlyContinue",
            f"    if (Test-Path -LiteralPath {_quote_ps(new_exe_path)}) {{ $moved = $true }}",
            "    else { Start-Sleep -Milliseconds 500 }",
            "}",
        ]
    )
    if old_exe_path:
        old_abs = os.path.abspath(old_exe_path)
        # Only remove the previous build when it uses the versioned name; a legacy
        # plain "PoeditCopilot.exe" may still be referenced by shortcuts.
        if is_versioned_exe_name(old_abs) and os.path.normcase(old_abs) != os.path.normcase(new_exe_path):
            lines.append(
                f"Remove-Item -LiteralPath {_quote_ps(old_abs)} -Force -ErrorAction SilentlyContinue"
            )
    lines.extend(
        [
            "if (Test-Path -LiteralPath " + _quote_ps(new_exe_path) + ") {",
            f"    Start-Process -FilePath {_quote_ps(new_exe_path)}",
            "}",
            f"Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
        ]
    )

    with open(script_path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write("\r\n".join(lines) + "\r\n")
    return script_path


def launch_swap_script(script_path):
    """Launch the swap helper fully hidden so it can run after this process exits."""
    powershell = (
        os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe",
        )
    )
    if not os.path.isfile(powershell):
        powershell = "powershell.exe"

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x00000008
    subprocess.Popen(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )
