from __future__ import annotations

import logging
import os
from io import BytesIO

import requests
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TDRC, TPE2, APIC, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.oggopus import OggOpus
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image

logger = logging.getLogger("cadenza")


class MetadataService:
    """Write metadata and cover art to audio files."""

    def write_tags(self, file_path: str, track_data: dict) -> None:
        """Write metadata tags to an audio file.

        Args:
            file_path: Path to the audio file.
            track_data: Dict with keys: title, artist, album, track_number, release_date, image_url.
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".mp3":
            self._write_mp3_tags(file_path, track_data)
        elif ext == ".opus" or ext == ".ogg":
            self._write_opus_tags(file_path, track_data)
        elif ext == ".m4a":
            self._write_m4a_tags(file_path, track_data)
        else:
            logger.warning("Unsupported format for tagging: %s", ext)

    def save_cover_art(self, album_dir: str, image_url: str) -> None:
        """Download and save cover.jpg in the album directory."""
        if not image_url:
            return

        cover_path = os.path.join(album_dir, "cover.jpg")
        if os.path.exists(cover_path):
            return

        try:
            image_data = self._download_image(image_url)
            if image_data:
                with open(cover_path, "wb") as f:
                    f.write(image_data)
                logger.debug("Saved cover art: %s", cover_path)
        except Exception as e:
            logger.warning("Failed to save cover art: %s", e)

    def _write_mp3_tags(self, file_path: str, data: dict) -> None:
        """Write ID3 tags to MP3 file."""
        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = ID3()

        tags.clear()

        if data.get("title"):
            tags.add(TIT2(encoding=3, text=data["title"]))
        if data.get("artist"):
            tags.add(TPE1(encoding=3, text=data["artist"]))
            tags.add(TPE2(encoding=3, text=data["artist"]))
        if data.get("album"):
            tags.add(TALB(encoding=3, text=data["album"]))
        if data.get("track_number"):
            tags.add(TRCK(encoding=3, text=str(data["track_number"])))
        if data.get("release_date"):
            tags.add(TDRC(encoding=3, text=data["release_date"]))

        # Embed cover art
        if data.get("image_url"):
            image_data = self._download_image(data["image_url"])
            if image_data:
                tags.add(APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,  # Front cover
                    desc="Cover",
                    data=image_data,
                ))

        tags.save(file_path)
        logger.debug("MP3 tags written: %s", file_path)

    def _write_opus_tags(self, file_path: str, data: dict) -> None:
        """Write Vorbis comments to Opus/OGG file."""
        try:
            audio = OggOpus(file_path)
        except Exception:
            logger.warning("Cannot write tags to %s", file_path)
            return

        if data.get("title"):
            audio["title"] = data["title"]
        if data.get("artist"):
            audio["artist"] = data["artist"]
        if data.get("album"):
            audio["album"] = data["album"]
        if data.get("track_number"):
            audio["tracknumber"] = str(data["track_number"])
        if data.get("release_date"):
            audio["date"] = data["release_date"]

        audio.save()
        logger.debug("Opus tags written: %s", file_path)

    def _write_m4a_tags(self, file_path: str, data: dict) -> None:
        """Write MP4 tags to M4A file."""
        try:
            audio = MP4(file_path)
        except Exception:
            logger.warning("Cannot write tags to %s", file_path)
            return

        if data.get("title"):
            audio["\xa9nam"] = [data["title"]]
        if data.get("artist"):
            audio["\xa9ART"] = [data["artist"]]
        if data.get("album"):
            audio["\xa9alb"] = [data["album"]]
        if data.get("track_number"):
            audio["trkn"] = [(data["track_number"], 0)]
        if data.get("release_date"):
            audio["\xa9day"] = [data["release_date"]]

        # Embed cover art
        if data.get("image_url"):
            image_data = self._download_image(data["image_url"])
            if image_data:
                audio["covr"] = [MP4Cover(image_data, imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()
        logger.debug("M4A tags written: %s", file_path)

    @staticmethod
    def _download_image(url: str, max_size: int = 800) -> bytes | None:
        """Download an image and resize it for embedding."""
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()

            img = Image.open(BytesIO(resp.content))
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Resize if too large
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size), Image.LANCZOS)

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=90)
            return buffer.getvalue()
        except Exception as e:
            logger.warning("Failed to download image %s: %s", url, e)
            return None
