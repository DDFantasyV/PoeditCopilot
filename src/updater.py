from datetime import datetime, timezone

import httpx
from PyQt6.QtCore import QThread, pyqtSignal

try:
    from version import __version__ as APP_VERSION
except ImportError:  # Only happens when the module is imported outside src/.
    APP_VERSION = "0.0.0"


GITHUB_REPO = "DDFantasyV/PoeditCopilot"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
EXE_DOWNLOAD_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/PoeditCopilot.exe"
CHECKSUM_DOWNLOAD_URL = f"{EXE_DOWNLOAD_URL}.sha256"

CHECK_TIMEOUT_SECONDS = 10.0
DEFAULT_INTERVAL_HOURS = 24


class UpdateCheckError(Exception):
    """Raised when the latest release version cannot be determined."""


class UpdateInfo:
    """Result of a successful update check."""

    def __init__(self, current_version, latest_version, release_url, published_at="", notes=""):
        self.current_version = current_version
        self.latest_version = latest_version
        self.release_url = release_url or RELEASES_PAGE
        self.published_at = published_at
        self.notes = notes

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
