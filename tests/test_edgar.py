import numpy as np
import pandas as pd

from alphadesk.data import edgar

# Two quarters of net income. Q1 is filed in a 10-Q, then restated in a 10-K
# filed later. On any date before the 10-K, only the original value is known.
FACTS = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
    {"start": "2025-01-01", "end": "2025-03-31", "val": 100, "form": "10-Q", "filed": "2025-05-05", "fy": 2025, "fp": "Q1"},
    {"start": "2025-04-01", "end": "2025-06-30", "val": 120, "form": "10-Q", "filed": "2025-08-04", "fy": 2025, "fp": "Q2"},
    {"start": "2025-01-01", "end": "2025-03-31", "val": 90, "form": "10-K", "filed": "2026-02-20", "fy": 2025, "fp": "FY"},
]}}}}}


def test_first_filing_wins():
    s = edgar.first_filed(FACTS, "NetIncomeLoss")
    q1 = s[s["end"] == "2025-03-31"]
    assert len(q1) == 1 and q1["val"].iloc[0] == 100   # the restatement does not rewrite history


def test_value_is_known_the_day_after_filing():
    s = edgar.first_filed(FACTS, "NetIncomeLoss")
    d = pd.to_datetime(["2025-05-05", "2025-05-06", "2025-08-04", "2025-08-05"])
    v = edgar.as_known_on(s, pd.DatetimeIndex(d), quarterly_only=True)
    assert np.isnan(v[0]) and v[1] == 100 and v[2] == 100 and v[3] == 120
