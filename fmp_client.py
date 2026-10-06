"""Financial Modeling Prep (FMP) REST client — Premium, Canadian coverage (owner, 2026-10-06).

One small reader for the stable API. The key lives where the other keys live:
$RB_STATE_DIR/secrets/fmp_api_key (0600, gitignored) or FMP_API_KEY. The key
travels in the URL, so a failure is reported as a code and NEVER with the URL
or the provider's body (house rule 1, and day-112b's credential rule).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://financialmodelingprep.com/stable/'
TIMEOUT = 20.0
RETRY_STATUSES = {429, 500, 502, 503, 504}


def load_key(state_dir=None):
    """The environment wins; the private file populates it."""
    present = os.environ.get('FMP_API_KEY', '').strip()
    if present:
        return present
    root = Path(state_dir or os.environ.get('RB_STATE_DIR') or '.rb-state')
    path = root/'secrets'/'fmp_api_key'
    if not path.is_file():
        return None
    key = path.read_text().strip()
    if not key or len(key) > 200 or any(c.isspace() for c in key):
        raise ValueError('INVALID_PRIVATE_CREDENTIAL')
    os.environ['FMP_API_KEY'] = key
    return key


class FMPError(ValueError):
    pass


def get(path, key=None, *, timeout=TIMEOUT, retries=1, opener=None, **params):
    """GET BASE+path?params&apikey → parsed JSON. Raises FMPError('FMP_<CODE>')."""
    key = key or load_key()
    if not key:
        raise FMPError('FMP_NO_CREDENTIAL')
    query = urllib.parse.urlencode({**{k: v for k, v in params.items() if v is not None},
                                    'apikey': key})
    url = BASE + path + '?' + query
    opener = opener or urllib.request.urlopen
    for attempt in range(retries + 1):
        try:
            with opener(url, timeout=timeout) as response:
                body = response.read().decode('utf-8')
            data = json.loads(body)
            if isinstance(data, dict) and data.get('Error Message'):
                raise FMPError('FMP_REFUSED')
            return data
        except urllib.error.HTTPError as exc:
            code = 'FMP_HTTP_%d' % exc.code
            if exc.code in RETRY_STATUSES and attempt < retries:
                time.sleep(2.0)
                continue
            raise FMPError(code) from None
        except FMPError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < retries:
                time.sleep(1.0)
                continue
            raise FMPError('FMP_TRANSPORT_' + type(exc).__name__.upper()[:30]) from None
        except ValueError:
            raise FMPError('FMP_BAD_JSON') from None
    raise FMPError('FMP_UNREACHABLE')
