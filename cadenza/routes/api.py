import logging

from flask import Blueprint, jsonify, render_template, request

from cadenza.extensions import db
from cadenza.models import Playlist, Track, SyncLog

logger = logging.getLogger("cadenza")

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/sync/status")
def sync_status():
    """Return current sync status as HTML partial for HTMX polling."""
    from cadenza.services.sync import get_sync_service

    sync_service = get_sync_service()
    status = sync_service.status

    # Add last completed sync info
    last_log = SyncLog.query.filter(
        SyncLog.status.in_(["completed", "cancelled"])
    ).order_by(SyncLog.finished_at.desc()).first()

    if last_log and last_log.finished_at:
        status["last_completed"] = last_log.finished_at.strftime("%H:%M:%S")
        status["last_downloaded"] = last_log.tracks_downloaded
        status["last_skipped"] = last_log.tracks_skipped
        status["last_errors"] = last_log.tracks_error + last_log.tracks_not_found
    else:
        status["last_completed"] = None

    return render_template("partials/sync_status.html", sync=status)


@api_bp.route("/sync/all", methods=["POST"])
def sync_all():
    """Trigger sync for all auto-sync playlists."""
    from cadenza.services.sync import get_sync_service

    sync_service = get_sync_service()

    if sync_service.is_running:
        return jsonify({"error": "A sync is already in progress."}), 409

    sync_service.start_all_sync()
    return jsonify({"status": "started"})


@api_bp.route("/sync/stop", methods=["POST"])
def sync_stop():
    """Cancel running sync."""
    from cadenza.services.sync import get_sync_service

    sync_service = get_sync_service()
    sync_service.cancel()

    return jsonify({"status": "cancelled"})


@api_bp.route("/playlists/<int:playlist_id>/tracks")
def playlist_tracks(playlist_id):
    """Return track table rows as HTML partial for HTMX live updates."""
    page = request.args.get("page", 1, type=int)
    playlist = db.get_or_404(Playlist, playlist_id)
    tracks = playlist.tracks.order_by(Track.track_number.asc(), Track.title.asc()).paginate(
        page=page, per_page=50, error_out=False
    )
    rows = ""
    for track in tracks.items:
        rows += render_template("partials/track_row.html", track=track)
    return rows


@api_bp.route("/playlists/<int:playlist_id>/counts")
def playlist_counts(playlist_id):
    """Return status counts as HTML partial for HTMX live updates."""
    status_counts = dict(
        db.session.query(Track.status, db.func.count(Track.id))
        .filter(Track.playlist_id == playlist_id)
        .group_by(Track.status)
        .all()
    )
    return render_template("partials/status_counts.html", status_counts=status_counts)


@api_bp.route("/tracks/<int:track_id>/retry", methods=["POST"])
def retry_track(track_id):
    """Reset a failed track for retry."""
    track = db.get_or_404(Track, track_id)
    track.status = "pending"
    track.error_message = None
    track.youtube_id = None
    db.session.commit()

    return render_template("partials/track_row.html", track=track)


@api_bp.route("/logs")
def logs():
    """Return recent sync logs."""
    sync_logs = SyncLog.query.order_by(SyncLog.started_at.desc()).limit(20).all()
    return render_template("partials/sync_logs.html", logs=sync_logs)
