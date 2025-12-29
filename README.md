# Emby2Trakt

A lightweight webhook service that syncs Emby media playback events to Trakt.tv. Automatically marks content as watched, manages favorites, and handles collection updates.

## Features

- 🎬 **Playback Tracking**: Automatically marks episodes and movies as watched when playback completes
- ⭐ **Favorites Sync**: Syncs favorite status between Emby and Trakt
- 📚 **Collection Management**: Automatically adds/removes content from Trakt collection
- 🔄 **Auto Token Refresh**: Automatically refreshes OAuth tokens when expired
- 🛡️ **Graceful Degradation**: Server starts even if Trakt is not configured
- 📊 **Health Monitoring**: Health endpoint for monitoring service status
- 🔒 **Secure**: Redacts sensitive information from logs

## Supported Events

- `playback.start` - Playback started
- `playback.stop` - Playback stopped (marks as watched)
- `playback.progress` - Playback progress (marks as watched at 80%+)
- `playback.pause` / `playback.unpause` - Playback paused/unpaused
- `item.markplayed` - Item marked as played
- `item.markunplayed` - Item marked as unplayed
- `item.rate` - Item favorited/unfavorited

## Requirements

- Python 3.11+
- Docker & Docker Compose (optional, for containerized deployment)
- Trakt.tv OAuth application credentials

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/soukron/emby2trakt.git
cd emby2trakt
```

### 2. Configure Trakt OAuth

1. Create a Trakt application at https://trakt.tv/oauth/applications
2. Set redirect URI to: `urn:ietf:wg:oauth:2.0:oob`
3. Copy `config.example` to `config.env`:
   ```bash
   cp config.example config.env
   ```
4. Edit `config.env` and add your Trakt credentials:
   ```
   TRAKT_CLIENT_ID=your_client_id
   TRAKT_CLIENT_SECRET=your_client_secret
   ```

### 3. Get OAuth Tokens

Run the token generator script:

```bash
python3 src/get_trakt_token.py
```

Follow the instructions to authorize the application and get your access/refresh tokens. Add them to `config.env`.

### 4. Run with Docker Compose

```bash
docker compose up -d
```

### 5. Configure Emby Webhook

In your Emby server settings, add a webhook pointing to:
- `https://your-domain/webhook` (or `/`)

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TRAKT_CLIENT_ID` | Trakt OAuth client ID | Yes |
| `TRAKT_CLIENT_SECRET` | Trakt OAuth client secret | Yes |
| `TRAKT_ACCESS_TOKEN` | Trakt OAuth access token | Yes |
| `TRAKT_REFRESH_TOKEN` | Trakt OAuth refresh token | Yes |
| `HOST` | Server host (default: `0.0.0.0`) | No |
| `PORT` | Server port (default: `5000`) | No |
| `LOG_LEVEL` | Logging level: DEBUG, INFO, WARNING, ERROR (default: `INFO`) | No |

### Docker Compose

The included `docker-compose.yml` sets up:
- Traefik reverse proxy with Let's Encrypt SSL
- IP whitelist middleware for webhook endpoint
- Health and refresh-token endpoints without IP restrictions

Adjust the IP whitelist in `docker-compose.yml` (line 62) to match your Emby server IP.

## API Endpoints

### `POST /webhook` or `POST /`
Receives webhooks from Emby and processes them.

**Response:**
```json
{
  "status": "success",
  "message": "Registered: Series Name S01E01"
}
```

### `GET /health`
Health check endpoint. Returns service status and Trakt configuration status.

**Response:**
```json
{
  "status": "ok",
  "trakt_configured": true,
  "trakt_token_valid": true
}
```

### `GET/POST /refresh-token`
Manually refresh the Trakt OAuth token. Useful for cron jobs.

**Response:**
```json
{
  "status": "success",
  "message": "Token refreshed successfully"
}
```

### `GET /`
Service information and supported events.

## Development

### Local Development

1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r src/requirements.txt
   ```

3. Run the application:
   ```bash
   python src/app.py
   ```

## Architecture

The application is built with:
- **Flask**: Web framework
- **Trakt API**: Official Trakt.tv Python library
- **Requests**: HTTP client for API calls

Key design decisions:
- Unified `TraktClient` class for all Trakt operations
- Generic methods that work for both episodes and movies
- Automatic token refresh on 401 errors
- Rate limiting (1 req/s for write operations)
- Graceful handling of missing configuration

## Logging

Logs follow a unified format:
```
IP - TIMESTAMP - LEVEL - MESSAGE
```

Example:
```
172.22.0.3 - 29/Dec/2025 09:30:23.914 - INFO - Event: playback.stop, Media: Breaking Bad S01E01
```

Sensitive information (tokens, API keys) is automatically redacted from logs.

## Troubleshooting

### Server won't start
- Check that `config.env` exists and contains required variables
- Server will start even without Trakt config, but sync will be disabled

### Webhooks not syncing
- Check `/health` endpoint to verify Trakt configuration
- Verify Emby webhook is pointing to correct URL
- Check logs for error messages
- Ensure IP whitelist allows your Emby server IP (if using Traefik)

### Token expired
- Tokens refresh automatically on 401 errors
- Use `/refresh-token` endpoint to manually refresh
- If refresh fails, run `get_trakt_token.py` to get new tokens

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- [Trakt.tv](https://trakt.tv) for the excellent API
- [Emby](https://emby.media) for the media server platform

