from datetime import datetime, timezone

from cadenza.extensions import db


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Setting {self.key}>"


class Playlist(db.Model):
    __tablename__ = "playlists"

    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(1000), nullable=True)
    owner = db.Column(db.String(200), nullable=True)
    track_count = db.Column(db.Integer, default=0)
    synced_count = db.Column(db.Integer, default=0)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    auto_sync = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tracks = db.relationship("Track", backref="playlist", cascade="all, delete-orphan", lazy="dynamic")
    sync_logs = db.relationship("SyncLog", backref="playlist", cascade="all, delete-orphan", lazy="dynamic")

    def __repr__(self):
        return f"<Playlist {self.name}>"


class Track(db.Model):
    __tablename__ = "tracks"
    __table_args__ = (db.UniqueConstraint("playlist_id", "spotify_id", name="uq_playlist_track"),)

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlists.id"), nullable=False)
    spotify_id = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    artist = db.Column(db.String(500), nullable=False)
    album = db.Column(db.String(500), nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    track_number = db.Column(db.Integer, nullable=True)
    release_date = db.Column(db.String(20), nullable=True)
    isrc = db.Column(db.String(20), nullable=True)
    image_url = db.Column(db.String(1000), nullable=True)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    error_message = db.Column(db.Text, nullable=True)
    youtube_id = db.Column(db.String(20), nullable=True)
    file_path = db.Column(db.String(1000), nullable=True)
    downloaded_at = db.Column(db.DateTime, nullable=True)
    retry_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Track {self.artist} - {self.title}>"


class SyncLog(db.Model):
    __tablename__ = "sync_logs"

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlists.id"), nullable=True)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="running", nullable=False)
    tracks_total = db.Column(db.Integer, default=0)
    tracks_downloaded = db.Column(db.Integer, default=0)
    tracks_skipped = db.Column(db.Integer, default=0)
    tracks_not_found = db.Column(db.Integer, default=0)
    tracks_error = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<SyncLog {self.id} {self.status}>"
