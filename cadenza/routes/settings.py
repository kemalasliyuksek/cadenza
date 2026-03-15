from __future__ import annotations

import json
import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from cadenza.extensions import db
from cadenza.models import Setting

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

# Default settings with their types and defaults
DEFAULTS = {
    "spotify_client_id": "",
    "spotify_client_secret": "",
    "spotify_redirect_uri": "http://127.0.0.1:8811/settings/spotify/callback",
    "spotify_access_token": "",
    "spotify_refresh_token": "",
    "spotify_token_expiry": "",
    "audio_format": "mp3",
    "audio_quality": "320k",
    "sync_schedule": "0 1 * * *",
    "output_template": "{artist}/{artist} - {album}/{track_number:02d} - {title}",
}


def get_setting(key: str, default: str | None = None) -> str:
    """Get a setting value from the database."""
    setting = db.session.get(Setting, key)
    if setting is None:
        return default if default is not None else DEFAULTS.get(key, "")
    return setting.value or ""


def set_setting(key: str, value: str) -> None:
    """Set a setting value in the database."""
    setting = db.session.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=value)
        db.session.add(setting)
    else:
        setting.value = value
    db.session.commit()


@settings_bp.route("/")
def index():
    settings = {key: get_setting(key) for key in DEFAULTS}
    spotify_connected = bool(settings.get("spotify_refresh_token"))
    return render_template("settings.html", settings=settings, spotify_connected=spotify_connected)


@settings_bp.route("/", methods=["POST"])
def save():
    for key in ["spotify_client_id", "spotify_client_secret", "spotify_redirect_uri",
                "audio_format", "audio_quality", "sync_schedule", "output_template"]:
        value = request.form.get(key, "").strip()
        if value or key in ("spotify_client_id", "spotify_client_secret"):
            set_setting(key, value)

    # Update scheduler if schedule changed
    from cadenza.scheduler.jobs import update_schedule
    update_schedule(get_setting("sync_schedule"))

    flash("Settings saved.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/spotify/auth")
def spotify_auth():
    """Initiate Spotify OAuth flow."""
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    client_id = get_setting("spotify_client_id")
    client_secret = get_setting("spotify_client_secret")

    if not client_id or not client_secret:
        flash("Please enter your Spotify Client ID and Secret first.", "error")
        return redirect(url_for("settings.index"))

    state = secrets.token_urlsafe(16)
    session["spotify_oauth_state"] = state

    redirect_uri = get_setting("spotify_redirect_uri", "http://127.0.0.1:8811/settings/spotify/callback")

    oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="playlist-read-private playlist-read-collaborative",
        state=state,
    )

    return redirect(oauth.get_authorize_url())


@settings_bp.route("/spotify/callback")
def spotify_callback():
    """Handle Spotify OAuth callback."""
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    state = request.args.get("state")
    if state != session.pop("spotify_oauth_state", None):
        flash("Invalid OAuth state. Please try again.", "error")
        return redirect(url_for("settings.index"))

    code = request.args.get("code")
    if not code:
        error = request.args.get("error", "Unknown error")
        flash(f"Spotify authorization failed: {error}", "error")
        return redirect(url_for("settings.index"))

    redirect_uri = get_setting("spotify_redirect_uri", "http://127.0.0.1:8811/settings/spotify/callback")

    oauth = SpotifyOAuth(
        client_id=get_setting("spotify_client_id"),
        client_secret=get_setting("spotify_client_secret"),
        redirect_uri=redirect_uri,
        scope="playlist-read-private playlist-read-collaborative",
    )

    token_info = oauth.get_access_token(code)

    set_setting("spotify_access_token", token_info["access_token"])
    set_setting("spotify_refresh_token", token_info["refresh_token"])
    set_setting("spotify_token_expiry", str(token_info["expires_at"]))

    flash("Spotify connected successfully.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/spotify/disconnect", methods=["POST"])
def spotify_disconnect():
    """Clear Spotify tokens."""
    for key in ("spotify_access_token", "spotify_refresh_token", "spotify_token_expiry"):
        set_setting(key, "")
    flash("Spotify disconnected.", "success")
    return redirect(url_for("settings.index"))
