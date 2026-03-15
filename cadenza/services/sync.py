from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

from cadenza.extensions import db
from cadenza.models import Playlist, Track, SyncLog
from cadenza.services.downloader import DownloaderService, DownloadError
from cadenza.services.matcher import MatcherService
from cadenza.services.metadata import MetadataService
from cadenza.utils.helpers import sanitize_filename

logger = logging.getLogger("cadenza")

# Module-level singleton
_sync_service = None


def get_sync_service():
    """Get the global SyncService instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service


class SyncService:
    """Orchestrates the full sync pipeline: fetch → match → download → tag."""

    # Delay between downloads to avoid rate limiting
    DOWNLOAD_DELAY = 3

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel_flag = False
        self._pause_flag = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._status = {
            "running": False,
            "paused": False,
            "playlist_name": None,
            "current_track": None,
            "progress": 0,
            "total": 0,
        }
        self._app = None

    def init_app(self, app):
        """Store app reference for background thread context."""
        self._app = app

    @property
    def is_running(self) -> bool:
        return self._status["running"]

    @property
    def status(self) -> dict:
        s = self._status.copy()
        s["percent"] = round(s["progress"] / s["total"] * 100) if s["total"] > 0 else 0
        return s

    def cancel(self):
        """Signal the current sync to stop."""
        self._cancel_flag = True
        self._pause_event.set()  # Unpause so thread can exit

    def pause(self):
        """Pause the current sync."""
        self._pause_flag = True
        self._pause_event.clear()
        self._status["paused"] = True

    def resume(self):
        """Resume a paused sync."""
        self._pause_flag = False
        self._pause_event.set()
        self._status["paused"] = False

    def start_playlist_sync(self, playlist_id: int) -> None:
        """Start a sync for a single playlist in a background thread."""
        from flask import current_app
        app = current_app._get_current_object()
        self._app = app
        thread = threading.Thread(target=self._run_sync, args=([playlist_id],), daemon=True)
        thread.start()

    def start_all_sync(self) -> None:
        """Start a sync for all auto-sync playlists in a background thread."""
        from flask import current_app
        app = current_app._get_current_object()
        self._app = app
        thread = threading.Thread(target=self._run_all_sync, daemon=True)
        thread.start()

    def _run_all_sync(self):
        """Sync all auto-sync playlists."""
        with self._app.app_context():
            playlist_ids = [
                p.id for p in Playlist.query.filter_by(auto_sync=True).all()
            ]
        if playlist_ids:
            self._run_sync(playlist_ids)

    def _run_sync(self, playlist_ids: list[int]):
        """Main sync loop. Runs in a background thread."""
        if not self._lock.acquire(blocking=False):
            logger.warning("Sync already in progress, skipping")
            return

        try:
            self._cancel_flag = False
            self._pause_flag = False
            self._pause_event.set()
            self._status["running"] = True
            self._status["paused"] = False

            for playlist_id in playlist_ids:
                if self._cancel_flag:
                    break
                self._sync_single_playlist(playlist_id)

        finally:
            self._status.update(running=False, paused=False, playlist_name=None, current_track=None, progress=0, total=0)
            self._pause_event.set()
            self._lock.release()

    def _sync_single_playlist(self, playlist_id: int):
        """Sync a single playlist: refresh from Spotify, then download pending tracks."""
        with self._app.app_context():
            playlist = db.session.get(Playlist, playlist_id)
            if not playlist:
                return

            self._status["playlist_name"] = playlist.name

            # Refresh playlist from Spotify (add new tracks)
            try:
                self._refresh_playlist(playlist)
            except Exception as e:
                logger.error("Failed to refresh playlist '%s': %s", playlist.name, e)

            # Get pending and retryable tracks
            tracks = Track.query.filter(
                Track.playlist_id == playlist_id,
                Track.status.in_(["pending", "not_found", "error"]),
                Track.retry_count < 3,
            ).all()

            if not tracks:
                logger.info("No pending tracks for '%s'", playlist.name)
                return

            # Create sync log
            sync_log = SyncLog(
                playlist_id=playlist_id,
                tracks_total=len(tracks),
            )
            db.session.add(sync_log)
            db.session.commit()

            self._status["total"] = len(tracks)
            self._status["progress"] = 0

            matcher = MatcherService()
            downloader = DownloaderService()
            metadata_service = MetadataService()

            from cadenza.routes.settings import get_setting
            music_path = self._app.config.get("MUSIC_PATH", "/music")
            audio_format = get_setting("audio_format", "mp3")
            audio_quality = get_setting("audio_quality", "320k")
            output_template = get_setting(
                "output_template", "{artist}/{artist} - {album}/{track_number:02d} - {title}"
            )

            for i, track in enumerate(tracks):
                # Wait if paused
                self._pause_event.wait()

                if self._cancel_flag:
                    logger.info("Sync cancelled")
                    break

                self._status["progress"] = i + 1
                self._status["current_track"] = f"{track.artist} - {track.title}"

                try:
                    self._process_track(
                        track, matcher, downloader, metadata_service,
                        music_path, audio_format, audio_quality, output_template, sync_log,
                    )
                except Exception as e:
                    logger.error("Error processing track '%s - %s': %s", track.artist, track.title, e)
                    track.status = "error"
                    track.error_message = str(e)[:500]
                    track.retry_count += 1
                    sync_log.tracks_error += 1

                db.session.commit()

                # Rate limit
                if i < len(tracks) - 1:
                    time.sleep(self.DOWNLOAD_DELAY)

            # Finalize sync log
            sync_log.finished_at = datetime.now(timezone.utc)
            sync_log.status = "cancelled" if self._cancel_flag else "completed"

            # Update playlist stats
            playlist.last_synced_at = datetime.now(timezone.utc)
            playlist.synced_count = Track.query.filter_by(
                playlist_id=playlist_id, status="downloaded"
            ).count()

            db.session.commit()
            logger.info(
                "Sync completed for '%s': %d downloaded, %d skipped, %d not found, %d errors",
                playlist.name, sync_log.tracks_downloaded, sync_log.tracks_skipped,
                sync_log.tracks_not_found, sync_log.tracks_error,
            )

            # Post-sync: fix file ownership for Nextcloud compatibility
            if sync_log.tracks_downloaded > 0:
                self._run_post_sync_hooks(music_path)

    def _process_track(self, track: Track, matcher: MatcherService,
                       downloader: DownloaderService, metadata_service: MetadataService,
                       music_path: str, audio_format: str, audio_quality: str,
                       output_template: str, sync_log: SyncLog) -> None:
        """Process a single track: dedup → match → download → tag."""

        # Step 1: Check deduplication (same spotify_id already downloaded elsewhere)
        existing = Track.query.filter(
            Track.spotify_id == track.spotify_id,
            Track.status == "downloaded",
            Track.file_path.isnot(None),
            Track.id != track.id,
        ).first()

        if existing and existing.file_path and os.path.exists(os.path.join(music_path, existing.file_path)):
            track.status = "downloaded"
            track.file_path = existing.file_path
            track.downloaded_at = datetime.now(timezone.utc)
            sync_log.tracks_skipped += 1
            logger.debug("Dedup: '%s - %s' already exists", track.artist, track.title)
            return

        # Step 2: Match on YouTube Music
        if not track.youtube_id:
            youtube_id = matcher.find_match(track)
            if not youtube_id:
                track.status = "not_found"
                track.retry_count += 1
                sync_log.tracks_not_found += 1
                return
            track.youtube_id = youtube_id

        # Step 3: Build output path
        try:
            track_num = track.track_number or 0
            rel_path = output_template.format(
                artist=sanitize_filename(track.artist),
                album=sanitize_filename(track.album or "Unknown Album"),
                title=sanitize_filename(track.title),
                track_number=track_num,
            )
        except (KeyError, ValueError):
            rel_path = f"{sanitize_filename(track.artist)}/{sanitize_filename(track.artist)} - {sanitize_filename(track.album or 'Unknown Album')}/{track_num:02d} - {sanitize_filename(track.title)}"

        full_path = os.path.join(music_path, rel_path)

        # Check if file already exists
        expected_file = f"{full_path}.{audio_format}"
        if os.path.exists(expected_file):
            track.status = "downloaded"
            track.file_path = f"{rel_path}.{audio_format}"
            track.downloaded_at = datetime.now(timezone.utc)
            sync_log.tracks_skipped += 1
            return

        # Step 4: Download
        track.status = "downloading"
        db.session.commit()

        downloaded_path = downloader.download(
            track.youtube_id, full_path, audio_format, audio_quality
        )

        # Step 5: Write metadata
        track_data = {
            "title": track.title,
            "artist": track.artist,
            "album": track.album,
            "track_number": track.track_number,
            "release_date": track.release_date,
            "image_url": track.image_url,
        }
        metadata_service.write_tags(downloaded_path, track_data)

        # Save cover.jpg in album directory
        album_dir = os.path.dirname(downloaded_path)
        metadata_service.save_cover_art(album_dir, track.image_url)

        # Step 6: Update track record
        track.status = "downloaded"
        track.file_path = os.path.relpath(downloaded_path, music_path)
        track.downloaded_at = datetime.now(timezone.utc)
        sync_log.tracks_downloaded += 1

        logger.info("Downloaded: %s - %s", track.artist, track.title)

    def _refresh_playlist(self, playlist: Playlist) -> None:
        """Refresh playlist metadata and add new tracks from Spotify."""
        from cadenza.services.spotify import SpotifyService

        spotify = SpotifyService()
        playlist_data = spotify.fetch_playlist(playlist.spotify_id)

        playlist.name = playlist_data["name"]
        playlist.description = playlist_data.get("description", "")
        playlist.image_url = playlist_data.get("image_url")
        playlist.track_count = playlist_data.get("track_count", 0)

        existing_spotify_ids = {t.spotify_id for t in playlist.tracks}

        for track_data in playlist_data.get("tracks", []):
            if track_data["spotify_id"] not in existing_spotify_ids:
                track = Track(
                    playlist_id=playlist.id,
                    spotify_id=track_data["spotify_id"],
                    title=track_data["title"],
                    artist=track_data["artist"],
                    album=track_data.get("album", ""),
                    duration_ms=track_data.get("duration_ms"),
                    track_number=track_data.get("track_number"),
                    release_date=track_data.get("release_date"),
                    isrc=track_data.get("isrc"),
                    image_url=track_data.get("image_url"),
                    status="pending",
                )
                db.session.add(track)

        db.session.commit()

    @staticmethod
    def _run_post_sync_hooks(music_path: str) -> None:
        """Run configurable post-sync commands from settings."""
        from cadenza.routes.settings import get_setting

        commands_str = get_setting("post_sync_commands", "")
        if not commands_str.strip():
            return

        for line in commands_str.strip().splitlines():
            cmd = line.strip()
            if not cmd or cmd.startswith("#"):
                continue
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    logger.info("Post-sync hook OK: %s", cmd)
                else:
                    logger.warning("Post-sync hook failed: %s → %s", cmd, result.stderr.strip())
            except Exception as e:
                logger.warning("Post-sync hook error: %s → %s", cmd, e)
