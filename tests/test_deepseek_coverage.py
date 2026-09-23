"""Model requests, usable evidence and threshold passes retain distinct counts."""
import copy

import pytest

import brief
import daily_render
import deepseek_factors as D
import email_render
from report_store import encode
from test_deepseek_factors import NOW, assessment, save, snapshot
from test_deepseek_render import report
from grounded_helpers import snapshot_receipt
from grounded_records import merge_grounding


def render_factor(snapshot, monkeypatch):
    digest = report()
    digest['intraday']['deepseek'] = snapshot
    before = encode(digest)
    def forbidden(*args, **kwargs):
        pytest.fail('rendering reacquired or reranked saved evidence')
    monkeypatch.setattr(D, 'load_prepared', forbidden)
    monkeypatch.setattr(D, 'research_watchlist', forbidden)
    monkeypatch.setattr(D, 'rank_shadow', forbidden)
    concise = email_render.text(digest)
    full = brief.render_text(digest)
    html = brief.render_html(digest)
    assert encode(digest) == before
    assert len(daily_render.deepseek_summary(digest['intraday'])) <= 6
    return concise, full, html


def test_zero_assessments_keeps_requested_pool_and_does_not_score_threshold(tmp_path, monkeypatch):
    obj = snapshot(tuple(f'NAME{i:02}.TO' for i in range(21)))
    obj.update(status='UNAVAILABLE', assessments=[], batches=[], covered=0,
               gaps=['Public input acquisition timed out; no model request was made.'])
    obj.update(private_grounding_receipts=[], grounding=merge_grounding([]))
    save(tmp_path, obj)
    loaded = D.load_prepared(tmp_path, NOW)
    watch = loaded['research_watchlist']
    assert watch['requested'] == watch['input_complete'] == 21
    assert watch['assessed'] == watch['evaluated'] == 0
    assert watch['threshold_evaluated'] is False
    concise, full, html = render_factor(loaded, monkeypatch)
    # The FULL report keeps every count verbatim: 21 requested, 0 assessed, no
    # threshold scored. Nothing is lost.
    for body in (full, html):
        assert '0/21 assessed' in body
        assert 'Threshold NOT EVALUATED' in body
        assert '0/0 assessed names' not in body
        assert '0 clear absolute sentiment support' not in body
    # The CONCISE email omits the section when the layer produced nothing and
    # states the absence in one line instead of several UNAVAILABLE lines about
    # an experiment that changes no selection. The absence must still be there.
    # Day-114b: the email prints the shadow layer only when it produced a
    # lean; its failures are stated in full in the report.
    assert 'Headline sentiment' not in concise and 'NO EDGE' not in concise
    assert 'NOT EVALUATED' in full
def test_failed_public_evidence_count_differs_from_no_model_response(tmp_path, monkeypatch):
    obj = snapshot(('A.TO', 'B.TO', 'C.TO'))
    obj.update(status='PARTIAL', covered=2,
               assessments=[assessment('A.TO','BULL',.7),assessment('B.TO','BEAR',-.4)])
    obj['candidate_gaps']['C.TO'] = ['MODEL_ASSESSMENT_UNAVAILABLE']
    snapshot_receipt(obj)
    save(tmp_path, obj)
    loaded = D.load_prepared(tmp_path, NOW)
    watch = loaded['research_watchlist']
    assert (watch['requested'],watch['input_complete'],watch['assessed'],
            watch['evaluated'],watch['eligible']) == (3,3,2,2,1)
    assert watch['threshold_evaluated'] is True
    concise, full, html = render_factor(loaded, monkeypatch)
    assert '2/3 assessed' in full
    assert '3 requested; 3 complete inputs; 2 model-assessed; 2 usable assessments' in full
    assert '1 of 2 usable assessments clear absolute sentiment support 0.50' in full
    assert 'Threshold NOT EVALUATED' not in concise


def test_candidate_only_failure_reaches_concise_view_without_fake_no_edge(tmp_path, monkeypatch):
    obj = snapshot(('A.TO',))
    obj['inputs']['candidates'][0]['technicals']['rsi'] = None
    from test_deepseek_factors import rehash
    rehash(obj)
    snapshot_receipt(obj)
    save(tmp_path, obj)
    loaded = D.load_prepared(tmp_path, NOW)
    assert loaded['gaps'] == []
    assert loaded['research_watchlist']['assessed'] == 1
    assert loaded['research_watchlist']['evaluated'] == 0
    concise, full, html = render_factor(loaded, monkeypatch)
    assert 'TECHNICAL_UNAVAILABLE:rsi' in full
    assert 'Threshold NOT EVALUATED' in full
    assert 'NO EDGE - WAIT' not in concise and 'NO EDGE - WAIT' not in full
    assert '0 complete inputs; 1 model-assessed; 0 usable assessments' in full


def test_unknown_input_coverage_is_not_relabelled_zero_or_complete():
    obj = D.unavailable('No snapshot was saved.', requested=21)
    assert obj['research_watchlist']['requested'] == 21
    assert obj['research_watchlist']['input_complete'] is None
    lines = daily_render._deepseek_detail({'deepseek': obj})
    assert any('21 requested; unknown complete inputs' in line for line in lines)


def test_evaluated_no_edge_has_scored_denominator_not_unavailable(tmp_path):
    obj = snapshot(('A.TO', 'B.TO'))
    obj['assessments'] = [assessment('A.TO','NO_EDGE',0.),assessment('B.TO','BULL',.4)]
    snapshot_receipt(obj)
    save(tmp_path, obj)
    loaded = D.load_prepared(tmp_path, NOW)
    before = copy.deepcopy(loaded)
    text = '\n'.join(daily_render._deepseek_detail({'deepseek': loaded}))
    assert loaded['research_watchlist']['decision'] == 'NO EDGE - WAIT'
    assert '0 of 2 usable assessments clear absolute sentiment support 0.50' in text
    assert 'Threshold NOT EVALUATED' not in text
    assert loaded == before
