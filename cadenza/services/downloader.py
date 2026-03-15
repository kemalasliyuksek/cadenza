from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger("cadenza")

COOKIES_SOURCE = "/app/cookies.txt"
COOKIES_WRITABLE = "/tmp/cookies.txt"


def _find_ytdlp() -> str:
    """Find the best available yt-dlp binary."""
    for path in ["/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp"]:
        if os.path.exists(path):
            return path
    return shutil.which("yt-dlp") or "yt-dlp"


def _get_cookies_path() -> str | None:
    """Get a writable cookies path. Copies from read-only mount if needed."""
    if os.path.exists(COOKIES_WRITABLE):
        return COOKIES_WRITABLE
    if os.path.exists(COOKIES_SOURCE):
        shutil.copy2(COOKIES_SOURCE, COOKIES_WRITABLE)
        return COOKIES_WRITABLE
    return None


class DownloaderService:
    """Download audio from YouTube Music using yt-dlp."""

    def download(self, youtube_id: str, output_path: str, audio_format: str = "mp3",
                 audio_quality: str = "320k") -> str:
        """Download a track from YouTube Music."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        url = f"https://music.youtube.com/watch?v={youtube_id}"
        output_template = f"{output_path}.%(ext)s"

        cmd = [
            _find_ytdlp(),
            "-x",
            "--audio-format", audio_format,
            "--audio-quality", "0",
            "--output", output_template,
            "--no-playlist",
            "--no-overwrites",
            "--retries", "3",
            "--quiet",
            url,
        ]

        cookies = _get_cookies_path()
        if cookies:
            cmd.insert(-1, "--cookies")
            cmd.insert(-1, cookies)

        logger.debug("Running: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            raise DownloadError(f"Download timed out for {youtube_id}")

        if result.returncode != 0:
            raise DownloadError(f"yt-dlp failed: {result.stderr.strip()}")

        # Find the actual output file
        expected_path = f"{output_path}.{audio_format}"
        if os.path.exists(expected_path):
            return expected_path

        base_dir = os.path.dirname(output_path)
        base_name = os.path.basename(output_path)
        for f in os.listdir(base_dir):
            if f.startswith(base_name) and not f.endswith(".part"):
                return os.path.join(base_dir, f)

        raise DownloadError(f"Downloaded file not found for {youtube_id}")


class DownloadError(Exception):
    """Raised when a download fails."""
    pass
