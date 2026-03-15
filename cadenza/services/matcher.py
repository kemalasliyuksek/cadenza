from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from ytmusicapi import YTMusic

from cadenza.models import Track

logger = logging.getLogger("cadenza")

# Singleton YTMusic instance (no auth needed for search)
_ytmusic = None


def _get_ytmusic() -> YTMusic:
    global _ytmusic
    if _ytmusic is None:
        _ytmusic = YTMusic()
    return _ytmusic


class MatcherService:
    """Match Spotify tracks to YouTube Music videos."""

    MATCH_THRESHOLD = 50

    def find_match(self, track: Track) -> str | None:
        """Find the best YouTube Music match for a track.

        Returns youtube_id if a good match is found, None otherwise.
        """
        ytmusic = _get_ytmusic()

        # Strategy 1: Search by ISRC (exact match)
        if track.isrc:
            youtube_id = self._search_by_isrc(ytmusic, track)
            if youtube_id:
                logger.debug("ISRC match for '%s - %s': %s", track.artist, track.title, youtube_id)
                return youtube_id

        # Strategy 2: Search by title + artist
        youtube_id = self._search_by_metadata(ytmusic, track)
        return youtube_id

    def _search_by_isrc(self, ytmusic: YTMusic, track: Track) -> str | None:
        """Try to find a match using ISRC code."""
        try:
            results = ytmusic.search(track.isrc, filter="songs", limit=1)
            if results:
                return results[0].get("videoId")
        except Exception as e:
            logger.debug("ISRC search failed for %s: %s", track.isrc, e)
        return None

    def _search_by_metadata(self, ytmusic: YTMusic, track: Track) -> str | None:
        """Search by title + artist and score results."""
        query = f"{track.title} {track.artist}"

        try:
            results = ytmusic.search(query, filter="songs", limit=10)
        except Exception as e:
            logger.warning("YouTube Music search failed for '%s': %s", query, e)
            return None

        if not results:
            logger.info("No YouTube Music results for '%s - %s'", track.artist, track.title)
            return None

        best_score = 0
        best_id = None

        for result in results:
            score = self._score_result(track, result)
            if score > best_score:
                best_score = score
                best_id = result.get("videoId")

        if best_score >= self.MATCH_THRESHOLD and best_id:
            logger.debug(
                "Match for '%s - %s': %s (score: %d)", track.artist, track.title, best_id, best_score
            )
            return best_id

        logger.info(
            "No good match for '%s - %s' (best score: %d)", track.artist, track.title, best_score
        )
        return None

    def _score_result(self, track: Track, result: dict) -> int:
        """Score a YouTube Music result against a Spotify track. Max 100."""
        score = 0

        # Title similarity (max 40)
        yt_title = result.get("title", "")
        title_sim = self._string_similarity(
            self._normalize_title(track.title), self._normalize_title(yt_title)
        )
        score += int(title_sim * 40)

        # Artist overlap (max 30)
        yt_artists = [a.get("name", "") for a in result.get("artists", [])]
        artist_sim = self._artist_similarity(track.artist, yt_artists)
        score += int(artist_sim * 30)

        # Duration closeness (max 20)
        yt_duration = result.get("duration_seconds")
        if yt_duration and track.duration_ms:
            diff = abs(track.duration_ms / 1000 - yt_duration)
            if diff < 3:
                score += 20
            elif diff < 10:
                score += 15
            elif diff < 30:
                score += 5

        # Album match bonus (max 10)
        yt_album = result.get("album", {})
        if yt_album and track.album:
            yt_album_name = yt_album.get("name", "") if isinstance(yt_album, dict) else str(yt_album)
            album_sim = self._string_similarity(track.album.lower(), yt_album_name.lower())
            score += int(album_sim * 10)

        return score

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Strip common suffixes like (feat. X), (Remastered), [Live], etc."""
        title = title.lower().strip()
        title = re.sub(r"\s*[\(\[].*?[\)\]]", "", title)
        title = re.sub(r"\s*-\s*remaster(ed)?.*$", "", title, flags=re.IGNORECASE)
        title = title.strip()
        return title

    @staticmethod
    def _string_similarity(a: str, b: str) -> float:
        """Return similarity ratio between 0 and 1."""
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    @staticmethod
    def _artist_similarity(spotify_artist: str, yt_artists: list[str]) -> float:
        """Compare Spotify artist string with YouTube Music artist list."""
        if not spotify_artist or not yt_artists:
            return 0.0

        # Spotify may have "Artist1, Artist2" format
        sp_artists = {a.strip().lower() for a in spotify_artist.split(",")}
        yt_set = {a.strip().lower() for a in yt_artists}

        if not sp_artists or not yt_set:
            return 0.0

        # Check overlap
        overlap = sp_artists & yt_set
        if overlap:
            return len(overlap) / max(len(sp_artists), len(yt_set))

        # Fuzzy match: check if any pair is similar
        best = 0.0
        for sp in sp_artists:
            for yt in yt_set:
                sim = SequenceMatcher(None, sp, yt).ratio()
                if sim > best:
                    best = sim
        return best
