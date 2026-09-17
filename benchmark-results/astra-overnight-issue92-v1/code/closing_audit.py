"""One deadline-triggered integrity audit; no progress events or model polling."""
import datetime
import time
from archive import ROOT, verify


if __name__=='__main__':
    deadline=datetime.datetime(2026,9,16,23,50,tzinfo=datetime.timezone.utc)
    delay=(deadline-datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if delay>0:
        time.sleep(delay)
    verify(ROOT/'closing_audit.json')
