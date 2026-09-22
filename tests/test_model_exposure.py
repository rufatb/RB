"""One bet written twice must be named as one bet (day-113 review, item 4)."""
import daily_render
import exposure
import report_page

SECTORS = {'SU.TO': {'sector': 'Energy'}, 'CNQ.TO': {'sector': 'Energy'},
           'DOL.TO': {'sector': 'Consumer Defensive'}, 'STN.TO': {'sector': 'Industrials'}}

# The real 2026-09-22 DeepSeek picks, reasons verbatim.
TODAY = {'status': 'READY', 'model': 'deepseek-flash', 'considered': 77,
         'longs': [{'ticker': 'DOL.TO', 'confidence': 0.56, 'reason': 'closed above orb_high'},
                   {'ticker': 'STN.TO', 'confidence': 0.53, 'reason': 'gap +0.85% with rvol 1.48'}],
         'shorts': [{'ticker': 'SU.TO', 'confidence': 0.62,
                     'reason': 'CA/CAD: WTI -5.98% overnight; SU gapped -0.83%'},
                    {'ticker': 'CNQ.TO', 'confidence': 0.60,
                     'reason': 'CA/CAD: WTI -5.98% overnight; CNQ gapped -1.05%'}],
         'comparison': {}}


def test_todays_two_oil_shorts_are_one_bet():
    groups = exposure.shared_exposure(TODAY, SECTORS)
    assert groups == [{'side': 'SHORT', 'sector': 'Energy',
                       'tickers': ['SU.TO', 'CNQ.TO'], 'driver': 'crude oil'}]


def test_different_sectors_are_not_flagged():
    assert all(g['side'] != 'LONG' for g in exposure.shared_exposure(TODAY, SECTORS))


def test_a_driver_is_named_only_when_every_pick_cites_it():
    snap = {**TODAY, 'shorts': [TODAY['shorts'][0], {**TODAY['shorts'][1], 'reason': 'macd negative'}]}
    assert exposure.shared_exposure(snap, SECTORS)[0]['driver'] is None


def test_both_renderers_print_it():
    snap = {**TODAY, 'shared_exposure': exposure.shared_exposure(TODAY, SECTORS)}
    text = '\n'.join(daily_render.opportunities_summary({'opportunities': snap}))
    assert 'SU.TO and CNQ.TO are all Energy' in text and 'ONE position' in text
    assert 'ONE position' in report_page._exposure(snap, 'DeepSeek')


def test_an_unknown_sector_map_degrades_to_saying_nothing():
    assert exposure.shared_exposure(TODAY, {}) == []
    assert exposure.load_sectors('/nonexistent.json') == {}
