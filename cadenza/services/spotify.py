import logging
import time

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from cadenza.extensions import db
from cadenza.models import Setting

logger = logging.getLogger("cadenza")


class SpotifyService:
    """Wrapper around spotipy for Spotify API access."""

    def get_client(self) -> spotipy.Spotify:
        """Return an authenticated Spotify client, refreshing token if needed."""
        from cadenza.routes.settings import get_setting, set_setting

        client_id = get_setting("spotify_client_id")
        client_secret = get_setting("spotify_client_secret")
        access_token = get_setting("spotify_access_token")
        refresh_token = get_setting("spotify_refresh_token")
        token_expiry = get_setting("spotify_token_expiry")
        redirect_uri = get_setting("spotify_redirect_uri", "http://127.0.0.1:8811/settings/spotify/callback")

        if not client_id or not client_secret:
            raise RuntimeError("Spotify Client ID and Secret are not configured.")

        if not refresh_token:
            raise RuntimeError("Spotify is not connected. Please authorize in Settings.")

        # Check if token needs refresh
        if token_expiry and float(token_expiry) < time.time():
            logger.info("Spotify token expired, refreshing...")
            oauth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope="playlist-read-private playlist-read-collaborative",
            )
            token_info = oauth.refresh_access_token(refresh_token)
            access_token = token_info["access_token"]
            set_setting("spotify_access_token", access_token)
            set_setting("spotify_token_expiry", str(token_info["expires_at"]))
            if "refresh_token" in token_info:
                set_setting("spotify_refresh_token", token_info["refresh_token"])

        return spotipy.Spotify(auth=access_token)

    def fetch_playlist(self, playlist_id: str) -> dict:
        """Fetch playlist metadata and all tracks from Spotify.

        Handles Spotify's 2026 API changes where the response uses 'items'
        instead of 'tracks' and track data is nested under 'item' instead of 'track'.
        """
        client = self.get_client()

        # Fetch full playlist (includes items inline)
        playlist = client.playlist(playlist_id)

        logger.debug("Spotify playlist response keys: %s", list(playlist.keys()))

        image_url = None
        if playlist.get("images"):
            image_url = playlist["images"][0]["url"]

        result = {
            "name": playlist.get("name", "Unknown Playlist"),
            "description": playlist.get("description", ""),
            "image_url": image_url,
            "owner": playlist.get("owner", {}).get("display_name", ""),
            "track_count": 0,
            "tracks": [],
        }

        # Spotify 2026 API: 'items' instead of 'tracks'
        items_data = playlist.get("items") or playlist.get("tracks")
        if not items_data:
            logger.warning("No items/tracks field in playlist response")
            return result

        result["track_count"] = items_data.get("total", 0)

        # Process paginated results
        while True:
            for entry in items_data.get("items", []):
                # Spotify 2026 API: track data under 'item' instead of 'track'
                track = entry.get("item") or entry.get("track")
                if not track or not track.get("id"):
                    continue

                artists = ", ".join(a["name"] for a in track.get("artists", []))
                album = track.get("album", {})
                album_name = album.get("name", "")
                album_images = album.get("images", [])
                album_image = album_images[0]["url"] if album_images else None

                isrc = None
                external_ids = track.get("external_ids", {})
                if external_ids:
                    isrc = external_ids.get("isrc")

                result["tracks"].append({
                    "spotify_id": track["id"],
                    "title": track["name"],
                    "artist": artists,
                    "album": album_name,
                    "duration_ms": track.get("duration_ms"),
                    "track_number": track.get("track_number"),
                    "release_date": album.get("release_date", ""),
                    "isrc": isrc,
                    "image_url": album_image,
                })

            # Next page
            next_url = items_data.get("next")
            if next_url:
                items_data = client._get(next_url)
            else:
                break

        logger.info("Fetched playlist '%s': %d tracks", result["name"], len(result["tracks"]))
        return result
