import logging

from flask import Blueprint, jsonify, render_template

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
    logs = SyncLog.query.order_by(SyncLog.started_at.desc()).limit(20).all()
    return render_template("partials/sync_logs.html", logs=logs)
