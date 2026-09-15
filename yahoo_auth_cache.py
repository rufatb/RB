"""Private, short-lived Yahoo authentication only; never market-price storage.

The cache can avoid cookie/crumb bootstrap inside the report's quote deadline.
It establishes neither endpoint entitlement nor a fresh/executable quote.
"""
from __future__ import annotations

import datetime as dt
import http.cookiejar
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
SCHEMA_VERSION = 1
MAX_AGE_SECONDS = 15 * 60
MAX_BYTES = 100_000
MAX_COOKIES = 32
CACHE_NAME = 'yahoo_auth.json'
COOKIE_FIELDS = frozenset({'version', 'name', 'value', 'domain', 'domain_specified',
                          'domain_initial_dot', 'path', 'path_specified', 'secure',
                          'expires', 'discard'})
FIELDS = frozenset({'schema_version', 'provider', 'session', 'prepared_at',
                    'expires_at', 'crumb', 'cookies'})


class AuthCacheError(ValueError):
    """A fixed reason code; no provider-controlled text or secrets."""


def _aware(value):
    try:
        value = dt.datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
        if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(ET)
    except (ValueError, TypeError, OverflowError):
        raise AuthCacheError('INVALID_AUTH_CLOCK') from None


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise AuthCacheError('DUPLICATE_AUTH_KEY')
        out[key] = value
    return out


def _bad_constant(_):
    raise AuthCacheError('INVALID_AUTH_NUMBER')


def _no_symlinks(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise AuthCacheError('UNSAFE_AUTH_PATH')


def _text(value, maximum, *, empty=False):
    return (isinstance(value, str) and (empty or bool(value)) and len(value) <= maximum
            and value.isascii() and all(32 <= ord(c) < 127 for c in value))


def _cookie(row, now):
    if not isinstance(row, dict) or set(row) != COOKIE_FIELDS:
        raise AuthCacheError('INVALID_COOKIE_SCHEMA')
    if (type(row['version']) is not int or row['version'] not in (0, 1)
            or not isinstance(row['name'], str)
            or re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}", row['name']) is None
            or not _text(row['value'], 8192, empty=True)):
        raise AuthCacheError('INVALID_COOKIE_VALUE')
    domain = row['domain']
    if (not isinstance(domain, str) or len(domain) > 253 or domain != domain.lower()
            or re.fullmatch(r'\.?[a-z0-9]+(?:[.-][a-z0-9]+)*', domain) is None
            or not (domain.lstrip('.') == 'yahoo.com' or domain.lstrip('.').endswith('.yahoo.com'))):
        raise AuthCacheError('INVALID_COOKIE_DOMAIN')
    for key in ('domain_specified', 'domain_initial_dot', 'path_specified', 'secure', 'discard'):
        if type(row[key]) is not bool:
            raise AuthCacheError('INVALID_COOKIE_FLAGS')
    if (row['domain_initial_dot'] != domain.startswith('.')
            or (row['domain_initial_dot'] and not row['domain_specified'])
            or not _text(row['path'], 1024) or not row['path'].startswith('/')):
        raise AuthCacheError('INVALID_COOKIE_PATH')
    expiry = row['expires']
    if expiry is not None:
        if type(expiry) is not int or not 0 < expiry < 253402300800:
            raise AuthCacheError('INVALID_COOKIE_EXPIRY')
        if expiry <= now.timestamp():
            raise AuthCacheError('EXPIRED_AUTH_COOKIE')
    return http.cookiejar.Cookie(port=None, port_specified=False, comment=None,
                                 comment_url=None, rest={}, rfc2109=False, **row)


def validate(document, now):
    now = _aware(now)
    if (not isinstance(document, dict) or set(document) != FIELDS
            or type(document['schema_version']) is not int or document['schema_version'] != SCHEMA_VERSION
            or document['provider'] != 'YahooFinance'):
        raise AuthCacheError('INVALID_AUTH_SCHEMA')
    prepared, expiry = _aware(document['prepared_at']), _aware(document['expires_at'])
    if document['session'] != now.date().isoformat() or prepared.date() != now.date():
        raise AuthCacheError('WRONG_AUTH_SESSION')
    if prepared > now:
        raise AuthCacheError('FUTURE_AUTH_CACHE')
    if not 0 < (expiry - prepared).total_seconds() <= MAX_AGE_SECONDS:
        raise AuthCacheError('INVALID_AUTH_TTL')
    if now >= expiry or (now - prepared).total_seconds() >= MAX_AGE_SECONDS:
        raise AuthCacheError('EXPIRED_AUTH_CACHE')
    crumb = document['crumb']
    if not _text(crumb, 256) or any(c.isspace() or c in '<>"' for c in crumb):
        raise AuthCacheError('INVALID_AUTH_CRUMB')
    rows = document['cookies']
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_COOKIES:
        raise AuthCacheError('INVALID_COOKIE_COUNT')
    jar, identities = http.cookiejar.CookieJar(), set()
    applicable = False
    for row in rows:
        cookie = _cookie(row, now)
        identity = cookie.domain, cookie.path, cookie.name
        if identity in identities:
            raise AuthCacheError('DUPLICATE_AUTH_COOKIE')
        identities.add(identity)
        if cookie.expires is not None and expiry.timestamp() > cookie.expires:
            raise AuthCacheError('AUTH_TTL_EXCEEDS_COOKIE')
        domain = cookie.domain.lstrip('.')
        if (domain == 'query2.finance.yahoo.com' or
                (cookie.domain_specified and 'query2.finance.yahoo.com'.endswith('.' + domain))):
            applicable = True
        jar.set_cookie(cookie)
    if not applicable:
        raise AuthCacheError('NO_QUOTE_HOST_COOKIE')
    return jar, crumb


def document(jar, crumb, now):
    """Serialize only authentication received by the caller's CookieJar."""
    now = _aware(now)
    rows = [{key: getattr(cookie, key) for key in COOKIE_FIELDS}
            for cookie in jar if not cookie.is_expired(now.timestamp())]
    expiry = min([now.timestamp() + MAX_AGE_SECONDS] +
                 [row['expires'] for row in rows if row['expires'] is not None])
    out = {'schema_version': SCHEMA_VERSION, 'provider': 'YahooFinance',
           'session': now.date().isoformat(), 'prepared_at': now.isoformat(),
           'expires_at': dt.datetime.fromtimestamp(expiry, ET).isoformat(),
           'crumb': crumb, 'cookies': rows}
    validate(out, now)
    return out


def private_atomic(path, value):
    """Write mode 0600 atomically; never follow a state-path symlink."""
    path = Path(path)
    _no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _no_symlinks(path)
    data = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True).encode()
    if len(data) > MAX_BYTES:
        raise AuthCacheError('OVERSIZED_AUTH_FILE')
    fd, temporary = tempfile.mkstemp(prefix='.auth-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _no_symlinks(path)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save(state_dir, value, now):
    validate(value, now)
    private_atomic(Path(state_dir) / 'secrets' / CACHE_NAME, value)


def load(state_dir, now=None):
    """Return private authentication separately from a safe public status."""
    now = _aware(now or dt.datetime.now(ET))
    status = {'status': 'NOT_PREPARED', 'reason_code': 'AUTH_CACHE_MISSING',
              'checked_at': now.isoformat(), 'session': now.date().isoformat(),
              'note': 'Authentication only; live quote access and BBO timestamps are not certified.'}
    if not state_dir:
        return None, status
    path = Path(state_dir) / 'secrets' / CACHE_NAME
    try:
        _no_symlinks(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise AuthCacheError('UNSAFE_AUTH_PERMISSIONS')
            if info.st_size > MAX_BYTES:
                raise AuthCacheError('OVERSIZED_AUTH_FILE')
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise AuthCacheError('OVERSIZED_AUTH_FILE')
        value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_bad_constant)
        result = validate(value, now)
        status.update(status='READY', reason_code='AUTH_CACHE_VALID',
                      prepared_at=value['prepared_at'], expires_at=value['expires_at'],
                      cookie_count=len(value['cookies']))
        return result, status
    except FileNotFoundError:
        return None, status
    except (AuthCacheError, OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, AuthCacheError) else 'AUTH_CACHE_READ_ERROR'
        status.update(status='STALE' if reason in {'EXPIRED_AUTH_CACHE', 'WRONG_AUTH_SESSION',
                                                  'EXPIRED_AUTH_COOKIE'} else 'INVALID', reason_code=reason)
        return None, status


def inspect(state_dir, now=None):
    """Read-only preflight hook, including a strictly sanitized last attempt."""
    now = _aware(now or dt.datetime.now(ET))
    result = load(state_dir, now)[1]
    if not state_dir:
        return result
    path = Path(state_dir) / 'yahoo_auth_status.json'
    try:
        _no_symlinks(path)
        if not path.exists():
            return result
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise AuthCacheError('INVALID_AUTH_RECEIPT')
        receipt = json.loads(path.read_bytes(), object_pairs_hook=_unique, parse_constant=_bad_constant)
        if not isinstance(receipt, dict):
            raise AuthCacheError('INVALID_AUTH_RECEIPT')
        checked = _aware(receipt.get('checked_at'))
        if checked > now or checked.date() != now.date():
            return result  # Retain the file; an old/future attempt is not today's result.
        statuses = {'READY', 'UNAVAILABLE'}
        reasons = {'AUTH_CACHE_VALID', 'AUTH_PREPARATION_TIMEOUT', 'AUTH_PREPARATION_UNAVAILABLE',
                   'AUTHENTICATION_ERROR', 'RATE_LIMITED', 'INVALID_PAYLOAD', 'TRANSPORT_TIMEOUT',
                   'TRANSPORT_ERROR', 'AUTH_CACHE_SAVE_ERROR', 'AUTH_PREPARATION_LOCAL_FAILURE',
                   'INVALID_AUTH_SCHEMA', 'INVALID_AUTH_CLOCK', 'WRONG_AUTH_SESSION',
                   'FUTURE_AUTH_CACHE', 'INVALID_AUTH_TTL', 'EXPIRED_AUTH_CACHE',
                   'INVALID_AUTH_CRUMB', 'INVALID_COOKIE_COUNT', 'INVALID_COOKIE_SCHEMA',
                   'INVALID_COOKIE_VALUE', 'INVALID_COOKIE_DOMAIN', 'INVALID_COOKIE_FLAGS',
                   'INVALID_COOKIE_PATH', 'INVALID_COOKIE_EXPIRY', 'EXPIRED_AUTH_COOKIE',
                   'DUPLICATE_AUTH_COOKIE', 'AUTH_TTL_EXCEEDS_COOKIE', 'NO_QUOTE_HOST_COOKIE',
                   'UNSAFE_AUTH_PATH', 'OVERSIZED_AUTH_FILE'}
        if receipt.get('status') not in statuses or receipt.get('reason_code') not in reasons:
            raise AuthCacheError('INVALID_AUTH_RECEIPT')
        last = {'status': receipt['status'], 'reason_code': receipt['reason_code'],
                'checked_at': checked.isoformat()}
        if type(receipt.get('http_status')) is int and 100 <= receipt['http_status'] <= 599:
            last['http_status'] = receipt['http_status']
        seconds = receipt.get('seconds')
        if type(seconds) in (int, float) and math.isfinite(seconds) and 0 <= seconds < 3600:
            last['seconds'] = seconds
        stages = receipt.get('stages')
        if isinstance(stages, list):
            last['stages'] = [s for s in stages[:8] if s in
                              ('yahoo_cookie_started', 'yahoo_cookie_completed',
                               'yahoo_crumb_started', 'yahoo_crumb_completed')]
        result['last_attempt'] = last
    except (AuthCacheError, OSError, ValueError, TypeError, UnicodeError, RecursionError):
        result['last_attempt'] = {'status': 'INVALID', 'reason_code': 'INVALID_AUTH_RECEIPT'}
    return result
