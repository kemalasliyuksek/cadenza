from flask import Blueprint, render_template

from cadenza.extensions import db
from cadenza.models import Playlist, Track, SyncLog

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    playlists = Playlist.query.order_by(Playlist.created_at.desc()).all()

    total_tracks = db.session.query(db.func.count(Track.id)).scalar() or 0
    downloaded_tracks = (
        db.session.query(db.func.count(Track.id)).filter(Track.status == "downloaded").scalar() or 0
    )
    pending_tracks = (
        db.session.query(db.func.count(Track.id)).filter(Track.status == "pending").scalar() or 0
    )

    recent_logs = SyncLog.query.order_by(SyncLog.started_at.desc()).limit(5).all()

    return render_template(
        "index.html",
        playlists=playlists,
        total_tracks=total_tracks,
        downloaded_tracks=downloaded_tracks,
        pending_tracks=pending_tracks,
        recent_logs=recent_logs,
    )


@main_bp.route("/health")
def health():
    return {"status": "ok"}, 200
