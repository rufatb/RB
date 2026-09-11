"""Descriptive risk evidence, computed once by brief; never selects or sizes."""
from collections import defaultdict
import math

# Public descriptive taxonomy. These labels do not configure an account or
# change the baseline's peer filter, selections or allocations.
DEFAULT_RISK_GROUPS = {
    'pipelines':['TRP.TO','ENB.TO'],
    'oil_producers':['CNQ.TO','SU.TO','CVE.TO'],
    'banks':['RY.TO','TD.TO','BNS.TO','BMO.TO','CM.TO'],
    'life_insurers':['SLF.TO','MFC.TO'],
    'telecoms':['BCE.TO','T.TO'],
    'railways':['CNR.TO','CP.TO'],
    'gold_miners':['ABX.TO','AEM.TO'],
}


def clustered_rate(rows):
    """Ratio of hits to legs, with session-clustered uncertainty.

    Sessions, not correlated names, supply independent observations. This is
    an approximate descriptive interval; serial dependence can widen it.
    """
    from scipy.stats import t
    groups = defaultdict(list)
    for row in rows:
        if str(row.get('hit')) in ('0', '1'):
            groups[row['date']].append(int(row['hit']))
    n = sum(map(len, groups.values()))
    hits = sum(map(sum, groups.values()))
    rate = hits / n if n else None
    g = len(groups)
    se = (math.sqrt(g / (g - 1) * sum((sum(v) - rate * len(v)) ** 2
          for v in groups.values())) / n) if g > 1 else None
    ci = [max(0, rate - t.ppf(.975, g - 1) * se),
          min(1, rate + t.ppf(.975, g - 1) * se)] if se is not None else None
    return dict(n=n, hits=hits, rate=rate, sessions=g, ci95=ci,
                mde80_pp=(3.5 + .8416212336) * se * 100 if se is not None else None)


def assess(pair_rows, legs, recorded_today, cfg):
    """Freeze historical evidence and today's common exposure, with gaps."""
    selected = legs or [dict(ticker=r['ticker'], side=r['side'],
                           baseline_shares=r.get('shares'),
                           signal_reference=r.get('p945'))
                        for r in recorded_today if r.get('role') == 'pair']
    rate = clustered_rate(pair_rows)
    groups = defaultdict(list)
    for row in pair_rows:
        groups[row['date']].append(row)
    distribution = [0] * (len(selected) + 1)
    excluded = 0
    for rows in groups.values():
        if (not selected or len(rows) != len(selected)
                or len({r['ticker'] for r in rows}) != len(rows)
                or any(str(r.get('hit')) not in ('0', '1') for r in rows)):
            excluded += 1
            continue
        distribution[sum(int(r['hit']) for r in rows)] += 1
    shape = dict(legs=len(selected), sessions=sum(distribution),
                 counts_by_hits=distribution, excluded_sessions=excluded,
                 bad_days=sum(distribution[:2]))
    calibration = []
    for lo, hi in ((.5, .55), (.55, .6), (.6, 1.000001)):
        matched = []
        for r in pair_rows:
            value = r.get('p_sided')
            if value not in (None, '') and lo <= float(value) < hi:
                matched.append(r)
        calibration.append(dict(score_band=f'{lo:.2f}–{min(hi, 1):.2f}',
                                **clustered_rate(matched)))
    # Diagnostic taxonomy only; never feeds peer filters, selection or weights.
    taxonomy = cfg.get('risk_groups', DEFAULT_RISK_GROUPS)
    notionals = []
    gaps = []
    for leg in selected:
        value = leg.get('baseline_alloc')
        if value is None:
            try:
                value = float(leg['baseline_shares']) * float(leg['signal_reference'])
            except (TypeError, ValueError):
                gaps.append(f"{leg['ticker']}: recorded notional unavailable")
                value = None
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError('invalid baseline notional in risk evidence')
        notionals.append(value)
    gross = sum(v for v in notionals if v is not None)
    concentration = []
    for group, names in taxonomy.items():
        for side in ('LONG', 'SHORT'):
            members = [(l, n) for l, n in zip(selected, notionals)
                       if l['ticker'] in names and l['side'] == side]
            if len(members) >= 2:
                complete = all(n is not None for _, n in members) and all(n is not None for n in notionals)
                share = sum(n for _, n in members) / gross if complete and gross else None
                side_notional = sum(n for l, n in zip(selected, notionals)
                                    if l['side'] == side and n is not None)
                side_share = sum(n for _, n in members) / side_notional if complete and side_notional else None
                concentration.append(dict(group=group, side=side,
                    tickers=[l['ticker'] for l, _ in members], gross_share=share,
                    side_share=side_share))
    return dict(rate=rate, day_shape=shape, calibration=calibration,
                concentration=concentration, gaps=gaps,
                label='Prior published gross bar proxies; no exact-fill or net-profit inference.')
