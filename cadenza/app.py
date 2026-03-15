import os

from flask import Flask

from cadenza.config import Config
from cadenza.extensions import db
from cadenza.utils.logger import setup_logging


def create_app() -> Flask:
    """Flask application factory."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure MUSIC_PATH is accessible from config
    app.config["MUSIC_PATH"] = Config.MUSIC_PATH

    # Setup logging
    setup_logging(Config.LOG_LEVEL)

    # Ensure data directory exists
    db_dir = os.path.dirname(Config.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    from cadenza.routes.main import main_bp
    from cadenza.routes.playlists import playlists_bp
    from cadenza.routes.settings import settings_bp
    from cadenza.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(playlists_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        # Enable WAL mode for better concurrent read performance
        with db.engine.connect() as conn:
            conn.execute(db.text("PRAGMA journal_mode=WAL"))
            conn.commit()

        # Create all tables
        db.create_all()

        # Initialize sync service with app context
        from cadenza.services.sync import get_sync_service
        sync_service = get_sync_service()
        sync_service.init_app(app)

        # Start scheduler (after tables exist)
        from cadenza.scheduler.jobs import setup_scheduler
        setup_scheduler(app)

    # Template helpers
    from cadenza.utils.helpers import format_duration

    @app.template_filter("duration")
    def duration_filter(ms):
        return format_duration(ms)

    return app
