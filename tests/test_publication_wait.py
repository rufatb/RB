import datetime as dt
from pathlib import Path
import pytest
from wait_for_publication import wait_until_entry, ET


def test_preparation_start_waits_until_entry_with_rechecked_clock():
    times = [dt.datetime(2026,9,10,9,45,58,tzinfo=ET)]
    sleeps=[]
    def sleep(n):
        sleeps.append(n)
        times[0] += dt.timedelta(seconds=n)
    result=wait_until_entry(lambda:times[0],sleep)
    assert result.time() == dt.time(9,46)
    assert sleeps == [1,1]


def test_late_start_does_not_backdate_or_wait():
    now=dt.datetime(2026,9,10,10,0,tzinfo=ET)
    assert wait_until_entry(lambda:now,lambda _:pytest.fail('late wait')) == now


def test_wrong_or_naive_preparation_clock_is_rejected():
    for now in (dt.datetime(2026,9,10,8,0,tzinfo=ET),dt.datetime(2026,9,10,9,45)):
        with pytest.raises(ValueError):
            wait_until_entry(lambda:now,lambda _:pytest.fail('invalid wait'))


def test_wrapper_waits_before_acquisition_and_uses_verified_interpreter():
    root=Path(__file__).resolve().parents[1]
    code='\n'.join(l for l in (root/'morning.sh').read_text().splitlines()
                   if not l.lstrip().startswith('#'))
    assert code.index('python runtime_check.py') < code.index('python wait_for_publication.py') < code.index('python daily_job.py')
    assert 'PATH=/opt/RB/.venv/bin:' in (root/'deploy/rb-report.service').read_text()
