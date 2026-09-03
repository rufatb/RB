"""Event-study dataset: 10 years of DAILY bars across a broad liquid US universe.

WHY DAILY: the 9:45 engine is capped at 60 days of 5-minute bars. Gap events
and multi-day holds are a DAILY-resolution question, and daily bars go back
decades — so for the first time in this project the data is not the binding
constraint.

SURVIVORSHIP BIAS (stated up front, cannot be fully removed): this universe is
today's list of tickers, so companies that gapped down and delisted are ABSENT.
That biases gap-DOWN results optimistically. Mitigations: a large-cap-weighted
list where delisting is rarer, and every result reported separately by gap
direction so the bias is visible rather than blended away.
"""
import os, time, requests, pandas as pd, numpy as np
from concurrent.futures import ThreadPoolExecutor
OUT = os.path.dirname(os.path.abspath(__file__))
H = {"User-Agent": "Mozilla/5.0"}

UNIVERSE = """
AAPL MSFT AMZN GOOGL META NVDA TSLA AVGO ORCL CRM ADBE AMD INTC QCOM TXN MU
JPM BAC WFC GS MS C SCHW AXP BLK SPGI CB PGR MMC
UNH JNJ LLY PFE MRK ABBV TMO ABT DHR BMY AMGN GILD CVS CI ELV ISRG SYK BSX MDT
VRTX REGN BIIB MRNA ILMN INCY EXEL NBIX SRPT ALNY IONS BMRN UTHR HALO
XOM CVX COP SLB EOG PSX VLO MPC OXY HES DVN FANG
HD LOW WMT TGT COST NKE SBUX MCD CMG TJX ROST DG DLTR
BA CAT DE HON GE LMT RTX UPS FDX UNP CSX NSC MMM EMR ETN
DIS NFLX CMCSA T VZ TMUS CHTR PARA WBD
PG KO PEP PM MO MDLZ CL KMB GIS K HSY
LIN APD SHW ECL NEM FCX NUE DOW
AMT PLD CCI EQIX SPG O PSA WELL
NEE DUK SO D AEP EXC XEL SRE PEG
V MA PYPL SQ COIN HOOD SOFI
UBER LYFT ABNB DASH SNAP PINS RBLX U DDOG SNOW NET CRWD ZS PANW FTNT MDB
""".split()

def daily(sym, tries=3):
    for host in ("query1", "query2"):
        for a in range(tries):
            try:
                r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                                 params={"interval": "1d", "range": "10y"},
                                 headers=H, timeout=45)
                res = (r.json().get("chart") or {}).get("result")
                if res: return res[0]
            except Exception:
                time.sleep(1.0 * (a + 1))
    return None

def one(s):
    res = daily(s)
    if not res: return None
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    if not ts: return None
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/New_York")
    df = pd.DataFrame({"o": q.get("open"), "h": q.get("high"), "l": q.get("low"),
                       "c": q.get("close"), "v": q.get("volume")},
                      index=[str(x.date()) for x in idx]).dropna(subset=["c", "o"])
    df["t"] = s
    df = df.reset_index().rename(columns={"index": "date"})
    return df

def build():
    """Harvest the panel. CALLED FROM __main__ ONLY (day-82).

    This ran at MODULE LEVEL: importing this file fired 133 threaded HTTP
    requests and wrote a 38MB csv. An inventory pass that merely imported every
    module to see which ones still load therefore triggered a full ten-year
    harvest as a side effect. Importing a module must never do that -- and a
    harness whose data appears by accident is one whose provenance nobody can
    state afterwards.
    """
    with ThreadPoolExecutor(max_workers=12) as ex:
        rows = [d for d in ex.map(one, UNIVERSE) if d is not None]
    print(f"fetched {len(rows)}/{len(UNIVERSE)} names")
    if not rows:
        raise SystemExit("no names fetched — refusing to write an empty panel")
    all_df = pd.concat(rows, ignore_index=True)
    out = f"{OUT}/daily.csv"
    all_df.to_csv(out, index=False)
    print(f"\ndaily set: {len(all_df):,} ticker-days, {all_df.t.nunique()} names, "
          f"{all_df.date.nunique()} sessions ({all_df.date.min()}..{all_df.date.max()})")
    print(f"wrote {out}")
    return all_df


if __name__ == "__main__":
    build()
