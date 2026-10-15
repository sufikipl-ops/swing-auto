# Backtest of the swing screen rules on NSE bhavcopy history.
# usage: python backtest.py <bhav_folder> <output_folder>
# Writes: backtest_summary.txt and backtest_trades.csv in <output_folder>
import csv, glob, os, sys, datetime, collections

bhav_dir = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

COST_PCT = 0.25      # rough round-trip delivery cost in % of entry
HOLD_DAYS = 5        # max holding days after entry
ENTRY_WINDOW = 4     # GTT valid for 4 trading days after signal
GAP_SKIP = 1.015     # skip if the stock opens > 1.5% above the trigger
ATR_STOP = 1.5       # stop = entry - 1.5 x ATR14
RR = 2.0             # target = 2 x risk


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


def ema(vals, span):
    a = 2.0 / (span + 1)
    e = vals[0]
    out = [e]
    for v in vals[1:]:
        e = a * v + (1 - a) * e
        out.append(e)
    return out


def rsi_series(cl):
    out = [None] * len(cl)
    au = ad = None
    n = 0
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]
        up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None:
            au, ad = up, dn
        else:
            au = (1 - 1 / 14.0) * au + (1 / 14.0) * up
            ad = (1 - 1 / 14.0) * ad + (1 / 14.0) * dn
        n += 1
        if n >= 14:
            out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


def adx_series(hi, lo, cl):
    n = 14
    N = len(cl)
    out = [None] * N
    if N < 2 * n + 1:
        return out
    pdm, mdm, trl = [], [], []
    for i in range(1, N):
        up = hi[i] - hi[i - 1]
        dn = lo[i - 1] - lo[i]
