import logging

from flask import Blueprint, render_template, request, redirect, url_for, flash

from cadenza.extensions import db
from cadenza.models import Playlist, Track
from cadenza.utils.helpers import parse_spotify_url

logger = logging.getLogger("cadenza")

playlists_bp = Blueprint("playlists", __name__, url_prefix="/playlists")


@playlists_bp.route("/")
def list_playlists():
    playlists = Playlist.query.order_by(Playlist.created_at.desc()).all()
    return render_template("playlists/list.html", playlists=playlists)


@playlists_bp.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "GET":
        return render_template("playlists/add.html")

    url = request.form.get("url", "").strip()
    if not url:
        flash("Please enter a Spotify playlist URL.", "error")
        return render_template("playlists/add.html")

    parsed = parse_spotify_url(url)
    if not parsed or parsed[0] != "playlist":
        flash("Invalid Spotify playlist URL.", "error")
        return render_template("playlists/add.html")

    spotify_type, spotify_id = parsed

    # Check if already exists
    existing = Playlist.query.filter_by(spotify_id=spotify_id).first()
    if existing:
        flash(f"Playlist '{existing.name}' is already added.", "error")
        return redirect(url_for("playlists.detail", playlist_id=existing.id))

    # Fetch from Spotify
    from cadenza.services.spotify import SpotifyService
    spotify = SpotifyService()

    try:
        playlist_data = spotify.fetch_playlist(spotify_id)
    except Exception as e:
        logger.error("Failed to fetch playlist %s: %s", spotify_id, e)
        flash(f"Failed to fetch playlist from Spotify: {e}", "error")
        return render_template("playlists/add.html")

    # Create playlist
    playlist = Playlist(
        spotify_id=spotify_id,
        name=playlist_data["name"],
        description=playlist_data.get("description", ""),
        image_url=playlist_data.get("image_url"),
        owner=playlist_data.get("owner", ""),
        track_count=playlist_data.get("track_count", 0),
    )
    db.session.add(playlist)
    db.session.flush()

    # Add tracks
    for track_data in playlist_data.get("tracks", []):
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

    flash(f"Added '{playlist.name}' with {playlist.track_count} tracks.", "success")
    return redirect(url_for("playlists.detail", playlist_id=playlist.id))


@playlists_bp.route("/<int:playlist_id>")
def detail(playlist_id):
    playlist = db.get_or_404(Playlist, playlist_id)
    page = request.args.get("page", 1, type=int)
    tracks = playlist.tracks.order_by(Track.id.asc()).paginate(
        page=page, per_page=50, error_out=False
    )
    status_counts = (
        db.session.query(Track.status, db.func.count(Track.id))
        .filter(Track.playlist_id == playlist_id)
        .group_by(Track.status)
        .all()
    )
    status_counts = dict(status_counts)
    return render_template(
        "playlists/detail.html", playlist=playlist, pagination=tracks,
        tracks=tracks.items, status_counts=status_counts,
        offset=(page - 1) * 50,
    )


@playlists_bp.route("/<int:playlist_id>/sync", methods=["POST"])
def sync(playlist_id):
    playlist = db.get_or_404(Playlist, playlist_id)

    from cadenza.services.sync import SyncService
    sync_service = SyncService()

    if sync_service.is_running:
        flash("A sync is already in progress.", "error")
        return redirect(url_for("playlists.detail", playlist_id=playlist_id))

    sync_service.start_playlist_sync(playlist_id)
    flash(f"Sync started for '{playlist.name}'.", "success")
    return redirect(url_for("playlists.detail", playlist_id=playlist_id))


@playlists_bp.route("/<int:playlist_id>/refresh", methods=["POST"])
def refresh(playlist_id):
    playlist = db.get_or_404(Playlist, playlist_id)

    from cadenza.services.spotify import SpotifyService
    spotify = SpotifyService()

    try:
        playlist_data = spotify.fetch_playlist(playlist.spotify_id)
    except Exception as e:
        flash(f"Failed to refresh: {e}", "error")
        return redirect(url_for("playlists.detail", playlist_id=playlist_id))

    # Update playlist metadata
    playlist.name = playlist_data["name"]
    playlist.description = playlist_data.get("description", "")
    playlist.image_url = playlist_data.get("image_url")
    playlist.track_count = playlist_data.get("track_count", 0)

    # Add new tracks (skip existing)
    existing_spotify_ids = {t.spotify_id for t in playlist.tracks}
    new_count = 0
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
            new_count += 1

    db.session.commit()
    flash(f"Refreshed '{playlist.name}'. {new_count} new tracks found.", "success")
    return redirect(url_for("playlists.detail", playlist_id=playlist_id))


@playlists_bp.route("/<int:playlist_id>/toggle-auto-sync", methods=["POST"])
def toggle_auto_sync(playlist_id):
    playlist = db.get_or_404(Playlist, playlist_id)
    playlist.auto_sync = not playlist.auto_sync
    db.session.commit()
    status = "enabled" if playlist.auto_sync else "disabled"
    flash(f"Auto-sync {status} for '{playlist.name}'.", "success")
    return redirect(url_for("playlists.detail", playlist_id=playlist_id))


@playlists_bp.route("/<int:playlist_id>/delete", methods=["POST"])
def delete(playlist_id):
    playlist = db.get_or_404(Playlist, playlist_id)
    name = playlist.name
    db.session.delete(playlist)
    db.session.commit()
    flash(f"Deleted '{name}'.", "success")
    return redirect(url_for("playlists.list_playlists"))
