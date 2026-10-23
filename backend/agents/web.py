"""Bounded Tavily Search transport. Returned snippets are untrusted evidence."""
import hashlib
import ipaddress
import json
import math
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import requests

ENDPOINT = 'https://api.tavily.com/search'
MAX_WEB_SEARCHES = 2
MAX_RESULTS = 4
MAX_RESPONSE_BYTES = 256_000


def web_search_enabled():
    key = os.getenv('TAVILY_API_KEY', '').strip()
    return bool(key and not key.lower().startswith(('replace_', 'your_', 'tvly-your')))


class WebSearchUnavailable(Exception):
    """Only a fixed, non-sensitive code may escape the transport."""
    def __init__(self, code, http_status=None):
        self.code = code if code in {'web_not_configured', 'web_provider_unavailable', 'web_timeout',
            'web_response_too_large', 'web_invalid_response', 'web_search_unavailable'} else 'web_search_unavailable'
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        super().__init__(self.code)


def public_url(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        if parts.scheme not in {'http', 'https'} or not host or parts.username or parts.password:
            return None
        if parts.port not in {None, 80, 443}:
            return None
        host = host.rstrip('.').lower()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.test', '.invalid')) or '.' not in host:
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            # Reject ambiguous numeric hosts, but allow ordinary public DNS names.
            if all(c in '0123456789.' for c in host):
                return None
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or '/', parts.query, ''))
    except (ValueError, UnicodeError):
        return None


def search_web(query, *, timeout=15):
    if not web_search_enabled():
        raise WebSearchUnavailable('web_not_configured')
    started = time.monotonic()
    timeout = max(.2, min(15.0, float(timeout)))
    connect = min(3.0, timeout / 3)
    payload = {'query': query, 'topic': 'general', 'search_depth': 'basic',
               'auto_parameters': False, 'max_results': MAX_RESULTS,
               'include_answer': False, 'include_raw_content': False,
               'include_images': False, 'include_usage': True}
    try:
        with requests.post(ENDPOINT, headers={'Authorization': 'Bearer ' + os.environ['TAVILY_API_KEY'].strip(),
                           'Content-Type': 'application/json'}, json=payload,
                           timeout=(connect, timeout - connect), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise WebSearchUnavailable('web_provider_unavailable', response.status_code)
            body = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if time.monotonic() - started >= timeout:
                    raise WebSearchUnavailable('web_timeout')
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise WebSearchUnavailable('web_response_too_large')
            data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            raise WebSearchUnavailable('web_invalid_response')
        passages, seen = [], set()
        now = datetime.now(timezone.utc).isoformat()
        for result in data['results'][:20]:
            if not isinstance(result, dict):
                continue
            url = public_url(result.get('url'))
            content = result.get('content')
            if not url or url in seen or not isinstance(content, str) or not content.strip():
                continue
            seen.add(url)
            title = result.get('title')
            passages.append({'reference': 'W' + hashlib.sha256(url.encode()).hexdigest()[:16],
                'url': url, 'title': title.strip()[:240] if isinstance(title, str) and title.strip() else urlsplit(url).hostname,
                'text': content.strip()[:1200], 'retrieved_at': now})
            if len(passages) == MAX_RESULTS:
                break
        credits = data.get('usage', {}).get('credits') if isinstance(data.get('usage'), dict) else None
        if type(credits) not in (int, float) or not math.isfinite(credits) or credits < 0:
            credits = None
        return {'source': 'web', 'status': 'searched' if passages else 'no_results',
                'passages': passages, 'credits': credits, 'untrusted_data': True}
    except WebSearchUnavailable:
        raise
    except requests.Timeout as error:
        raise WebSearchUnavailable('web_timeout') from error
    except (requests.RequestException, ValueError, TypeError, KeyError, OverflowError) as error:
        raise WebSearchUnavailable('web_search_unavailable') from error
