"""The names the report trades were the only ones with no live fallback.

THE DEFECT, from the 2026-09-15 email:

    deepseek-flash: UNAVAILABLE; 0/60 assessed.  prepared technicals 21.

`prepare_factor_pool` routed the twenty-one baseline names to the pre-open
intraday cache and, on a miss, marked each BASELINE_HISTORY_UNAVAILABLE and
DROPPED it — "do not repeat the baseline provider's failed staging work".
Research names, by contrast, already fell through to `pending` and were
fetched live. So the twenty-one names the report actually trades were the
twenty-one guaranteed to be excluded on any morning the pre-open job had not
run, which is every morning, because the host has never been installed.

Reproduced end to end through `diagnose_deepseek_pipeline` on a cache staged
for another session:

    before:  verified 30/60, complete technicals 7,  assessed 6
    after:   verified 51/60, complete technicals 27, assessed 22

Caching "changes acquisition only, not baseline features or rules"
(CLAUDE.md), so a live fetch inside the same budget yields the same
technicals. The degradation is recorded per ticker and summarised in the
email: a reuse gap means a pre-open staging job did not run (house rule 1).
"""
import datetime as dt
import json
from zoneinfo import ZoneInfo

import prepare_factor_pool

ET = ZoneInfo('America/New_York')
NOW = dt.datetime(2026, 9, 15, 8, 30, tzinfo=ET)


def technicals(ticker):
    """A complete, valid row — what a live fetch is expected to return."""
    return {'ticker': ticker, 'technicals': {'vwap': 1.0, 'rsi': 50.0, 'macd': 0.0,
            'macd_signal': 0.0, 'macd_hist': 0.0, 'orb_high': 1.0, 'orb_low': 1.0,
            'rvol': 1.0}, 'technicals_as_of': NOW.isoformat()}


def stale_cache(root, cfg):
    """A pre-open cache staged for ANOTHER session — the live situation every
    morning the host has not staged one."""
    cache = root/'intraday_cache'
    cache.mkdir(parents=True, exist_ok=True)
    (cache/'manifest.json').write_text(json.dumps(
        {'complete': True, 'session': '2026-09-11', 'source': 'yahoo_direct',
         'tickers': cfg['scan']['universe'], 'prepared_at': '2026-09-11T08:05:00-04:00'}))


def run(tmp_path, universe, baseline):
    from diagnostic_context import create_context
    cfg = {'exchange_tz': 'America/New_York', 'scan': {'universe': baseline},
           'data_sources': {'primary': 'yahoo_direct'}}
    # prepare_diagnostic refuses to touch anything that looks like canonical
    # publication state, so give it the explicit isolated context it demands.
    tmp_path = tmp_path/'state'
    create_context(tmp_path, now=NOW)
    stale_cache(tmp_path, cfg)
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps({'research_universe': universe}))
    asked = []

    def fetcher(ticker, now):
        asked.append(ticker)
        return technicals(ticker)

    def acquire_fn(jobs, *a, **kw):
        return {t: {'status': 'OK', 'value': fn()} for t, (fn, *_rest) in jobs.items()}

    out = prepare_factor_pool.prepare_diagnostic(
        tmp_path, cfg, now=NOW, fetcher=fetcher, acquire_fn=acquire_fn)
    return out, asked


# ── the defect, behaviourally ─────────────────────────────────────────────

def test_baseline_names_are_fetched_live_when_the_cache_is_stale(tmp_path):
    """They used to be dropped outright. On a stale cache the twenty-one names
    the report trades must still reach the pool."""
    baseline = ['AC.TO', 'RY.TO', 'TD.TO']
    out, asked = run(tmp_path, baseline + ['BN.TO'], baseline)
    for ticker in baseline:
        assert ticker in asked, f'{ticker} was dropped instead of acquired live'
    # What this test pins is the ROUTING: a stale baseline cache must send the
    # ticker to live acquisition. Whether the fetched bytes then survive OHLCV
    # validation is the research-cache round-trip, covered by
    # test_factor_pool_day100 — this stub's rows deliberately do not carry a
    # provider receipt, so asserting on `verified` here would be asserting on
    # the fixture, not on the defect.
    assert out['reused_baseline'] == 0, 'a stale cache must not count as reuse'


def test_the_stale_reuse_is_recorded_per_ticker(tmp_path):
    """House rule 1: degrading is allowed, going quiet about it is not."""
    baseline = ['AC.TO', 'RY.TO']
    out, _ = run(tmp_path, baseline, baseline)
    gaps = out.get('cache_reuse_gaps') or {}
    assert set(gaps) >= set(baseline), gaps
    assert all('BASELINE_CACHE_REJECTED' in reason for reason in gaps.values())


def test_a_stale_cache_no_longer_produces_hard_errors(tmp_path):
    baseline = ['AC.TO', 'RY.TO']
    out, _ = run(tmp_path, baseline, baseline)
    assert 'BASELINE_HISTORY_UNAVAILABLE' not in json.dumps(out.get('errors') or {})


def test_a_usable_cache_is_still_reused_rather_than_refetched(tmp_path):
    """The fallback must not quietly replace the fast path — re-fetching a
    perfectly good cache would put the pre-open budget back on the network."""
    import inspect
    src = inspect.getsource(prepare_factor_pool._prepare)
    i = src.index("status['reused_baseline'] += 1")
    assert '_cached(' in src[max(0, i - 200):i],         'the cached branch must still be attempted before any live fetch'


def test_the_email_reports_the_degraded_pool_cache():
    import daily_render
    coverage = {'target': 150, 'master_eligible': 0, 'master_status': 'UNAVAILABLE',
                'pool_requested': 60, 'pool_status': 'PARTIAL', 'technical_complete': 27,
                'shortlisted': None, 'assessed': 22, 'mode': 'LEGACY_RESEARCH_FALLBACK',
                'pool': {'cache_reuse_gaps': {'AC.TO': 'BASELINE_CACHE_REJECTED_ValueError'}}}
    line = daily_render._expanded_summary({'research_coverage': coverage})
    assert 'DEGRADED for 1 name(s)' in line
    assert 'technicals unchanged' in line, \
        'the reader must be told the inputs themselves are not affected'


def test_a_healthy_pool_cache_says_nothing():
    import daily_render
    coverage = {'target': 150, 'master_eligible': 0, 'master_status': 'UNAVAILABLE',
                'pool_requested': 60, 'pool_status': 'PARTIAL', 'technical_complete': 27,
                'shortlisted': None, 'assessed': 22, 'mode': 'EXPANDED_TSX_RESEARCH',
                'pool': {'cache_reuse_gaps': {}}}
    assert 'DEGRADED' not in daily_render._expanded_summary({'research_coverage': coverage})
