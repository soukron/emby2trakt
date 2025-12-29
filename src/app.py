#!/usr/bin/env python3
"""
Emby to Trakt Webhook - Simplified Version
Receives webhooks from Emby and syncs to Trakt:
- Playback tracking (mark as watched)
- Manual played/unplayed marking
- Favorites management
"""

import os
import re
import json
import time
import logging
import threading
from datetime import datetime
from functools import wraps
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

from flask import Flask, request, jsonify
import requests

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    """Application configuration from environment variables."""
    client_id: str = os.getenv('TRAKT_CLIENT_ID', '')
    client_secret: str = os.getenv('TRAKT_CLIENT_SECRET', '')
    access_token: str = os.getenv('TRAKT_ACCESS_TOKEN', '')
    refresh_token: str = os.getenv('TRAKT_REFRESH_TOKEN', '')
    host: str = os.getenv('HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', 5000))
    log_level: str = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)
    
    @property
    def has_token(self) -> bool:
        return bool(self.access_token)


config = Config()


# ============================================================================
# LOGGING
# ============================================================================

def redact_sensitive(text: str) -> str:
    """Redact tokens and API keys from log messages."""
    if not text:
        return text
    patterns = [
        (r'Bearer\s+[A-Za-z0-9]+', 'Bearer <redacted>'),
        (r'trakt-api-key["\']?\s*[:=]\s*["\']?[A-Za-z0-9]+', 'trakt-api-key: <redacted>'),
        (r'client_id["\']?\s*[:=]\s*["\']?[A-Za-z0-9]+', 'client_id: <redacted>'),
        (r'client_secret["\']?\s*[:=]\s*["\']?[A-Za-z0-9]+', 'client_secret: <redacted>'),
        (r'refresh_token["\']?\s*[:=]\s*["\']?[A-Za-z0-9]+', 'refresh_token: <redacted>'),
        (r'access_token["\']?\s*[:=]\s*["\']?[A-Za-z0-9]+', 'access_token: <redacted>'),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


class UnifiedFormatter(logging.Formatter):
    """Unified log format: IP - TIMESTAMP - LEVEL - MESSAGE"""
    
    def format(self, record):
        # Get client IP from Flask context if available
        client_ip = 'unknown'
        try:
            from flask import has_request_context, request as flask_request
            if has_request_context():
                client_ip = flask_request.environ.get('HTTP_X_FORWARDED_FOR', 
                            flask_request.environ.get('REMOTE_ADDR', 'unknown')).split(',')[0].strip()
        except:
            pass
        
        # Timestamp with milliseconds
        dt = datetime.fromtimestamp(record.created)
        ms = int((record.created % 1) * 1000)
        timestamp = dt.strftime('%d/%b/%Y %H:%M:%S') + f'.{ms:03d}'
        
        # Handle Werkzeug logs specially
        msg = record.getMessage()
        if record.name == 'werkzeug':
            # Remove ANSI codes
            msg = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', msg)
            # Parse Werkzeug format
            match = re.match(r'^(\S+)\s+-\s+-\s+\[[^\]]+\]\s+"(\S+)\s+(\S+)\s+HTTP/[^"]+"\s+(\d+)', msg)
            if match:
                ip, method, path, status = match.groups()
                return f'{ip} - {timestamp} - {record.levelname} - "{method} {path}" {status}'
        
        return f'{client_ip} - {timestamp} - {record.levelname} - {redact_sensitive(msg)}'


def setup_logging():
    """Configure logging for all components."""
    level = getattr(logging, config.log_level, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(UnifiedFormatter())
    handler.setLevel(level)
    
    # Configure all relevant loggers
    for name in ['', __name__, 'werkzeug', 'requests', 'urllib3', 'trakt', 'trakt.core']:
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    
    return logging.getLogger(__name__)


logger = setup_logging()


# ============================================================================
# TRAKT CLIENT
# ============================================================================

class TraktClient:
    """Unified client for Trakt API operations."""
    
    BASE_URL = 'https://api.trakt.tv'
    
    def __init__(self):
        self.access_token = config.access_token
        self.refresh_token = config.refresh_token
        self._refresh_lock = threading.Lock()
        self._last_write_time = 0
        self._config_path = self._find_config_path()
    
    def _find_config_path(self) -> Optional[str]:
        """Find config.env file path."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            '/app/config.env',
            os.path.join(os.path.dirname(base_dir), 'config.env'),
            os.path.join(base_dir, 'config.env'),
            'config.env',
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return '/app/config.env' if os.path.exists('/app') else candidates[1]
    
    @property
    def headers(self) -> Dict[str, str]:
        """Standard Trakt API headers."""
        return {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': config.client_id,
            'Authorization': f'Bearer {self.access_token}'
        }
    
    def _rate_limit(self, method: str):
        """Enforce rate limiting for write operations."""
        if method.lower() in ['post', 'put', 'delete']:
            elapsed = time.time() - self._last_write_time
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            self._last_write_time = time.time()
    
    def request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                operation: str = "", max_retries: int = 3) -> Optional[requests.Response]:
        """Make an authenticated request to Trakt API with retry logic."""
        if not config.is_configured:
            logger.debug(f"Trakt not configured, skipping {operation}")
            return None
        
        url = f'{self.BASE_URL}/{endpoint.lstrip("/")}'
        self._rate_limit(method)
        token_refreshed = False
        
        for attempt in range(max_retries):
            try:
                headers = self.headers
                func = getattr(requests, method.lower())
                response = func(url, headers=headers, json=data) if data else func(url, headers=headers)
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 2))
                    logger.info(f"Rate limit hit for {operation}, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                
                # Handle token expiration
                if response.status_code == 401 and not token_refreshed:
                    logger.warning(f"Token expired for {operation}, refreshing...")
                    with self._refresh_lock:
                        if self._refresh_token():
                            token_refreshed = True
                            continue
                        return response
                
                return response
                
            except Exception as e:
                logger.error(f"Request error for {operation} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        
        return None
    
    def _refresh_token(self) -> bool:
        """Refresh the access token."""
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False
        
        try:
            response = requests.post(f'{self.BASE_URL}/oauth/token', json={
                'refresh_token': self.refresh_token,
                'client_id': config.client_id,
                'client_secret': config.client_secret,
                'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
                'grant_type': 'refresh_token'
            }, headers={'Content-Type': 'application/json'}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data['access_token']
                self.refresh_token = data.get('refresh_token', self.refresh_token)
                self._save_tokens()
                logger.info("Access token refreshed successfully")
                return True
            else:
                logger.error(f"Token refresh failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False
    
    def _save_tokens(self):
        """Save tokens to config.env file."""
        if not self._config_path:
            return
        try:
            with open(self._config_path, 'r') as f:
                lines = f.readlines()
            
            updated = []
            for line in lines:
                if line.startswith('TRAKT_ACCESS_TOKEN='):
                    updated.append(f'TRAKT_ACCESS_TOKEN={self.access_token}\n')
                elif line.startswith('TRAKT_REFRESH_TOKEN='):
                    updated.append(f'TRAKT_REFRESH_TOKEN={self.refresh_token}\n')
                else:
                    updated.append(line)
            
            with open(self._config_path, 'w') as f:
                f.writelines(updated)
            
            # Update environment
            os.environ['TRAKT_ACCESS_TOKEN'] = self.access_token
            os.environ['TRAKT_REFRESH_TOKEN'] = self.refresh_token
            
            logger.debug("Tokens saved to config.env")
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
    
    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------
    
    def search(self, query: str, media_type: str) -> Optional[Dict]:
        """Search for a show or movie on Trakt."""
        response = self.request('get', f'/search/{media_type}?query={query}', 
                               operation=f"search {media_type}")
        if response and response.status_code == 200:
            results = response.json()
            if results:
                return results[0].get(media_type if media_type != 'show' else 'show')
        return None
    
    # -------------------------------------------------------------------------
    # Collection Operations (unified for episodes and movies)
    # -------------------------------------------------------------------------
    
    def add_to_collection(self, media_info: Dict) -> bool:
        """Add episode or movie to collection."""
        payload = self._build_sync_payload(media_info)
        response = self.request('post', '/sync/collection', payload, 
                               operation="add to collection")
        return response is not None and response.status_code in [200, 201]
    
    def remove_from_collection(self, media_info: Dict) -> bool:
        """Remove episode or movie from collection."""
        payload = self._build_sync_payload(media_info)
        response = self.request('post', '/sync/collection/remove', payload,
                               operation="remove from collection")
        return response is not None and response.status_code in [200, 201, 204]
    
    # -------------------------------------------------------------------------
    # History Operations (watched status)
    # -------------------------------------------------------------------------
    
    def add_to_history(self, media_info: Dict) -> bool:
        """Mark episode or movie as watched."""
        payload = self._build_sync_payload(media_info)
        response = self.request('post', '/sync/history', payload,
                               operation="add to history")
        success = response is not None and response.status_code in [200, 201]
        if success:
            self.add_to_collection(media_info)
        return success
    
    def remove_from_history(self, media_info: Dict) -> bool:
        """Unmark episode or movie as watched."""
        payload = self._build_sync_payload(media_info)
        response = self.request('post', '/sync/history/remove', payload,
                               operation="remove from history")
        success = response is not None and response.status_code in [200, 201, 204]
        if success:
            self.remove_from_collection(media_info)
        return success
    
    # -------------------------------------------------------------------------
    # Favorites Operations
    # -------------------------------------------------------------------------
    
    def add_to_favorites(self, media_info: Dict) -> bool:
        """Add episode or movie to favorites."""
        payload = self._build_sync_payload(media_info)
        response = self.request('post', '/sync/favorites', payload,
                               operation="add to favorites")
        success = response is not None and response.status_code in [200, 201]
        if success:
            self.add_to_collection(media_info)
        return success
    
    def remove_from_favorites(self, media_info: Dict) -> bool:
        """Remove episode or movie from favorites."""
        payload = self._build_sync_payload(media_info)
        response = self.request('post', '/sync/favorites/remove', payload,
                               operation="remove from favorites")
        return response is not None and response.status_code in [200, 204]
    
    # -------------------------------------------------------------------------
    # Payload Builders
    # -------------------------------------------------------------------------
    
    def _build_ids(self, media_info: Dict) -> Dict:
        """Build IDs dict from media info."""
        ids = {}
        if media_info.get('tmdb_id'):
            ids['tmdb'] = int(media_info['tmdb_id'])
        if media_info.get('tvdb_id'):
            ids['tvdb'] = int(media_info['tvdb_id'])
        if media_info.get('imdb_id'):
            ids['imdb'] = media_info['imdb_id']
        return ids
    
    def _build_sync_payload(self, media_info: Dict) -> Dict:
        """Build sync payload for Trakt API."""
        ids = self._build_ids(media_info)
        
        if media_info['media_type'] == 'episode':
            # Need to search for the show first to get its title
            show_title = media_info.get('trakt_title') or media_info['series_name']
            return {
                'shows': [{
                    'title': show_title,
                    'ids': ids,
                    'seasons': [{
                        'number': media_info['season'],
                        'episodes': [{'number': media_info['episode']}]
                    }]
                }]
            }
        else:  # movie
            return {
                'movies': [{
                    'title': media_info.get('trakt_title') or media_info['title'],
                    'year': media_info.get('year'),
                    'ids': ids
                }]
            }
    
    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------
    
    def check_token(self) -> Tuple[bool, Optional[str]]:
        """Verify the access token is valid."""
        if not config.is_configured:
            return False, "Trakt client_id/client_secret not configured"
        if not self.access_token:
            return False, "No access token configured"
        
        response = self.request('get', '/users/settings', operation="health check")
        if response and response.status_code == 200:
            return True, None
        elif response and response.status_code == 401:
            return False, "Token invalid or expired"
        elif response:
            return False, f"API error: {response.status_code}"
        else:
            return False, "Connection error"


# Global client instance
trakt = TraktClient()


# ============================================================================
# WEBHOOK PROCESSING
# ============================================================================

SUPPORTED_EVENTS = [
    'playback.start', 'playback.stop', 'playback.progress',
    'playback.pause', 'playback.unpause',
    'item.markplayed', 'item.markunplayed', 'item.rate'
]


def parse_webhook(data: Dict) -> Optional[Dict]:
    """Parse Emby webhook data into standardized media info."""
    event_type = data.get('Event', '')
    if event_type not in SUPPORTED_EVENTS:
        return None
    
    item = data.get('Item', {})
    item_type = item.get('Type', '')
    provider_ids = item.get('ProviderIds', {})
    
    base_info = {
        'event_type': event_type,
        'tmdb_id': provider_ids.get('Tmdb'),
        'tvdb_id': provider_ids.get('Tvdb'),
        'imdb_id': provider_ids.get('Imdb'),
    }
    
    if item_type == 'Episode':
        return {
            **base_info,
            'media_type': 'episode',
            'series_name': item.get('SeriesName', ''),
            'season': item.get('ParentIndexNumber', 0),
            'episode': item.get('IndexNumber', 0),
            'title': item.get('Name', ''),
            'is_played': event_type == 'item.markplayed',
            'is_favorite': item.get('UserData', {}).get('IsFavorite', False),
        }
    
    elif item_type == 'Movie':
        year = item.get('ProductionYear') or item.get('PremiereDate', '')[:4]
        try:
            year = int(year) if year else None
        except:
            year = None
        
        return {
            **base_info,
            'media_type': 'movie',
            'title': item.get('Name', ''),
            'year': year,
            'is_played': event_type == 'item.markplayed',
            'is_favorite': item.get('UserData', {}).get('IsFavorite', False),
        }
    
    return None


def format_media_str(media_info: Dict) -> str:
    """Format media info for logging."""
    if media_info['media_type'] == 'episode':
        return f"{media_info['series_name']} S{media_info['season']:02d}E{media_info['episode']:02d}"
    else:
        year = f" ({media_info['year']})" if media_info.get('year') else ""
        return f"{media_info['title']}{year}"


def handle_playback(media_info: Dict, data: Dict) -> Tuple[Dict, int]:
    """Handle playback events (start, stop, progress)."""
    if not config.is_configured:
        return {'status': 'skipped', 'message': 'Trakt not configured'}, 200
    
    event_type = media_info['event_type']
    
    # Only mark as watched on stop or sufficient progress
    if event_type == 'playback.progress':
        progress = data.get('PlaybackPositionTicks', 0)
        runtime = data.get('Item', {}).get('RunTimeTicks', 1)
        if runtime > 0 and (progress / runtime) * 100 < 80:
            return {'status': 'pending', 'message': 'Insufficient progress'}, 200
    
    # Only mark as watched on stop or high progress
    if event_type not in ['playback.stop', 'playback.progress']:
        return {'status': 'pending', 'message': 'Waiting for playback completion'}, 200
    
    success = trakt.add_to_history(media_info)
    media_str = format_media_str(media_info)
    
    if success:
        return {'status': 'success', 'message': f"Registered: {media_str}"}, 200
    else:
        return {'status': 'error', 'message': f"Error registering in Trakt"}, 500


def handle_played_status(media_info: Dict) -> Tuple[Dict, int]:
    """Handle mark played/unplayed events."""
    if not config.is_configured:
        return {'status': 'skipped', 'message': 'Trakt not configured'}, 200
    
    is_played = media_info['is_played']
    media_str = format_media_str(media_info)
    
    if is_played:
        success = trakt.add_to_history(media_info)
        action = "marked"
    else:
        success = trakt.remove_from_history(media_info)
        action = "unmarked"
    
    if success:
        return {'status': 'success', 'message': f"{action.capitalize()} as watched: {media_str}"}, 200
    else:
        return {'status': 'error', 'message': f"Error {action} in Trakt"}, 500


def handle_favorite(media_info: Dict) -> Tuple[Dict, int]:
    """Handle favorite/unfavorite events."""
    if not config.is_configured:
        return {'status': 'skipped', 'message': 'Trakt not configured'}, 200
    
    is_favorite = media_info['is_favorite']
    media_str = format_media_str(media_info)
    
    if is_favorite:
        success = trakt.add_to_favorites(media_info)
        action = "marked"
    else:
        success = trakt.remove_from_favorites(media_info)
        action = "unmarked"
    
    if success:
        return {'status': 'success', 'message': f"{action.capitalize()} as favorite: {media_str}"}, 200
    else:
        return {'status': 'error', 'message': f"Error {action} favorite in Trakt"}, 500


# ============================================================================
# FLASK APPLICATION
# ============================================================================

app = Flask(__name__)
app.logger.setLevel(getattr(logging, config.log_level, logging.INFO))


@app.route('/webhook', methods=['POST'])
@app.route('/', methods=['POST'])
def webhook():
    """Main webhook endpoint for Emby events."""
    try:
        # Parse request data (Emby sends multipart/form-data)
        if request.is_json:
            data = request.get_json()
        elif request.content_type and 'multipart/form-data' in request.content_type:
            data = json.loads(request.form.get('data', '{}'))
        else:
            try:
                data = request.get_json(force=True)
            except:
                data = request.form.to_dict()
        
        media_info = parse_webhook(data)
        if not media_info:
            return jsonify({'status': 'ignored', 'message': 'Unsupported event or media type'}), 200
        
        event_type = media_info['event_type']
        media_str = format_media_str(media_info)
        logger.info(f"Event: {event_type}, Media: {media_str}")
        
        # Route to appropriate handler
        if event_type in ['item.markplayed', 'item.markunplayed']:
            result, status = handle_played_status(media_info)
        elif event_type == 'item.rate':
            result, status = handle_favorite(media_info)
        elif event_type in ['playback.stop', 'playback.progress', 'playback.start', 
                           'playback.pause', 'playback.unpause']:
            result, status = handle_playback(media_info, data)
        else:
            result, status = {'status': 'ignored', 'message': 'Unknown event'}, 200
        
        return jsonify(result), status
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/refresh-token', methods=['GET', 'POST'])
def refresh_token():
    """Manually refresh the Trakt OAuth token."""
    if not config.is_configured:
        return jsonify({
            'status': 'error',
            'message': 'Trakt not configured (missing client_id/client_secret)'
        }), 503
    
    try:
        logger.info("Manual token refresh requested")
        with trakt._refresh_lock:
            success = trakt._refresh_token()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Token refreshed successfully'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Could not refresh token'
            }), 500
            
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    valid, error = trakt.check_token()
    
    response = {
        'status': 'ok' if valid else 'error',
        'trakt_configured': config.is_configured,
        'trakt_token_valid': valid
    }
    
    if error:
        response['error'] = error
    
    return jsonify(response), 200 if valid else 503


@app.route('/', methods=['GET'])
def index():
    """Service information."""
    return jsonify({
        'service': 'Emby to Trakt Webhook',
        'version': '3.0.0',
        'supported_events': SUPPORTED_EVENTS,
        'endpoints': {
            'webhook': 'POST /webhook or /',
            'health': 'GET /health',
            'refresh_token': 'GET/POST /refresh-token'
        }
    }), 200


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    if not config.is_configured:
        logger.warning("TRAKT_CLIENT_ID and/or TRAKT_CLIENT_SECRET not configured - Trakt sync disabled")
    elif not config.has_token:
        logger.warning("TRAKT_ACCESS_TOKEN not configured - Trakt sync disabled")
    
    debug_mode = config.log_level == 'DEBUG'
    logger.info(f"Starting server on {config.host}:{config.port} (LOG_LEVEL={config.log_level})")
    app.run(host=config.host, port=config.port, debug=debug_mode)

