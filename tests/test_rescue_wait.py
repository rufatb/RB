import datetime as dt

import rescue_wait as W

ET = W.ET


def test_waits_the_seconds_asked_and_never_past_the_cap(capsys):
    slept = []
    assert W.main(['--seconds', '30'], sleep=slept.append,
                  clock=lambda: dt.datetime(2026, 11, 12, 9, 0, tzinfo=ET)) == 0
    assert slept == [30.0] and 'WAITED 30 s' in capsys.readouterr().out
    W.main(['--seconds', '900'], sleep=slept.append,
           clock=lambda: dt.datetime(2026, 11, 12, 9, 0, tzinfo=ET))
    assert slept[-1] == W.CAP          # a call never outlives the Bash tool's limit


def test_until_says_whether_the_time_has_come(capsys):
    times = iter([dt.datetime(2026, 11, 12, 9, 0, tzinfo=ET), dt.datetime(2026, 11, 12, 9, 1, 55, tzinfo=ET)])
    slept = []
    assert W.main(['--until', '09:12'], sleep=slept.append, clock=lambda: next(times)) == 2
    assert slept == [W.CAP] and 'STILL_BEFORE' in capsys.readouterr().out
    times = iter([dt.datetime(2026, 11, 12, 9, 13, tzinfo=ET)] * 2)
    assert W.main(['--until', '09:12'], sleep=slept.append, clock=lambda: next(times)) == 0
    assert slept[-1] == 0.0
