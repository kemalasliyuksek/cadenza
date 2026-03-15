# Cadenza

Self-hosted Spotify playlist sync — download your playlists from YouTube Music with full metadata.

Cadenza watches your Spotify playlists and automatically downloads new tracks from YouTube Music. Spotify provides the metadata (track names, album art, artist info), YouTube Music provides the audio. Your music, your server, no subscriptions.

## Features

- **Playlist sync** — Add Spotify playlist URLs, Cadenza downloads the tracks
- **Automatic scheduling** — Daily sync at a configurable time
- **Smart matching** — Finds the best YouTube Music match using title, artist, duration, and ISRC
- **Full metadata** — Embeds Spotify metadata (title, artist, album, cover art) into downloaded files
- **Deduplication** — Same track in multiple playlists is only downloaded once
- **Simple web UI** — Add playlists, monitor progress, view sync history
- **Docker ready** — Single container, deploy anywhere

## Quick Start

```bash
docker compose up -d
```

Open `http://localhost:8811`, configure your Spotify credentials, and add a playlist.

## Docker Compose

```yaml
services:
  cadenza:
    image: ghcr.io/kemalasliyuksek/cadenza:latest
    container_name: cadenza
    restart: unless-stopped
    ports:
      - "8811:8811"
    environment:
      - CADENZA_SECRET_KEY=change-me-to-a-random-string
    volumes:
      - cadenza_data:/app/data
      - /path/to/your/music:/music
volumes:
  cadenza_data:
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CADENZA_SECRET_KEY` | (required) | Flask session secret key |
| `CADENZA_DB_PATH` | `/app/data/cadenza.db` | SQLite database path |
| `CADENZA_MUSIC_PATH` | `/music` | Music download directory |
| `CADENZA_LOG_LEVEL` | `info` | Log level (debug/info/warning/error) |

### Spotify Setup

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new application
3. Add `http://localhost:8811/settings/spotify/callback` as a Redirect URI (or your domain)
4. Copy the Client ID and Client Secret
5. Enter them in Cadenza's Settings page

### Music Servers

Cadenza writes music files to a folder. Point your music server at the same folder:

- **Navidrome** — Mount the same volume as `/music:ro`
- **Jellyfin** — Add the folder as a music library
- **Plex** — Add the folder as a music library
- **Any server** — Any server that watches a folder for new music files

## Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
flask --app cadenza.app run --debug --port 8811
```

## License

MIT
