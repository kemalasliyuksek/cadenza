import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root for relative paths in development
_BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("CADENZA_SECRET_KEY", "dev-secret-change-me")
    MUSIC_PATH = os.environ.get("CADENZA_MUSIC_PATH", str(_BASE_DIR / "music"))
    LOG_LEVEL = os.environ.get("CADENZA_LOG_LEVEL", "info").upper()

    # DB path: absolute if provided, otherwise relative to project root
    _db_path = os.environ.get("CADENZA_DB_PATH", str(_BASE_DIR / "data" / "cadenza.db"))
    DB_PATH = _db_path if os.path.isabs(_db_path) else str(_BASE_DIR / _db_path)

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
