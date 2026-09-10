"""Wait through the final preparation minute; acquire no market data."""
import datetime as dt
import time
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')


def wait_until_entry(clock=None, sleeper=time.sleep):
    clock = clock or (lambda: dt.datetime.now(ET))
    while True:
        now = clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('aware publication clock required')
        now = now.astimezone(ET)
        remaining = (now.replace(hour=9,minute=46,second=0,microsecond=0)-now).total_seconds()
        if remaining <= 0:
            return now
        if remaining > 120:
            raise ValueError('start publication preparation at or after 09:44 ET')
        sleeper(min(remaining,1))


if __name__ == '__main__':
    print(wait_until_entry().isoformat())
