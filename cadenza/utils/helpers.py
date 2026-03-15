from __future__ import annotations

import re
import unicodedata


def parse_spotify_url(url: str) -> tuple[str, str] | None:
    """Extract type and ID from a Spotify URL or URI.

    Returns (type, id) tuple, e.g. ("playlist", "37i9dQZF1DXcBWIGoYBM5M")
    or None if the URL is not recognized.
    """
    # Spotify URI: spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
    uri_match = re.match(r"spotify:(playlist|album|track):([a-zA-Z0-9]+)", url.strip())
    if uri_match:
        return uri_match.group(1), uri_match.group(2)

    # Spotify URL: https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=...
    url_match = re.match(
        r"https?://open\.spotify\.com/(playlist|album|track)/([a-zA-Z0-9]+)", url.strip()
    )
    if url_match:
        return url_match.group(1), url_match.group(2)

    return None


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename.

    Removes or replaces characters that are not safe for filesystems.
    """
    # Normalize unicode
    name = unicodedata.normalize("NFC", name)

    # Replace path separators and other problematic characters
    name = re.sub(r'[<>:"/\\|?*]', "_", name)

    # Remove control characters
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)

    # Strip leading/trailing dots and spaces
    name = name.strip(". ")

    # Collapse multiple spaces/underscores
    name = re.sub(r"[_ ]{2,}", " ", name)

    # Limit length
    if len(name) > 200:
        name = name[:200].rstrip(". ")

    return name or "Unknown"


def format_duration(ms: int | None) -> str:
    """Format milliseconds as m:ss string."""
    if ms is None:
        return "--:--"
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"
