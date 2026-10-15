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
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
        trl.append(max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])))
    st, sp, sm = sum(trl[:n]), sum(pdm[:n]), sum(mdm[:n])
    dx = []
    # index in trl list k corresponds to bar k+1
    idx_bar = []
    for k in range(n - 1, len(trl)):
        if k >= n:
            st = st - st / n + trl[k]
            sp = sp - sp / n + pdm[k]
            sm = sm - sm / n + mdm[k]
        if st == 0:
            dx.append(0.0)
        else:
            pdi = 100.0 * sp / st
            mdi = 100.0 * sm / st
            s = pdi + mdi
            dx.append(0.0 if s == 0 else 100.0 * abs(pdi - mdi) / s)
        idx_bar.append(k + 1)
    if len(dx) < n:
        return out
    adx = sum(dx[:n]) / n
    out[idx_bar[n - 1]] = adx
    for j in range(n, len(dx)):
        adx = (adx * (n - 1) + dx[j]) / n
        out[idx_bar[j]] = adx
    return out


def macd_hist_series(cl):
    m = [a - b for a, b in zip(ema(cl, 12), ema(cl, 26))]
    s = ema(m, 9)
    return [x - y for x, y in zip(m, s)]# ---- load all bhavcopy files (EQ only)
data = collections.defaultdict(dict)
for f in glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv')):
    with open(f, newline='', encoding='utf-8', errors='ignore') as h:
        rd = csv.reader(h)
        next(rd, None)
        for r in rd:
            if len(r) < 15:
                continue
            r = [c.strip() for c in r]
            if r[1] != 'EQ':
                continue
            try:
                d = datetime.datetime.strptime(r[2], '%d-%b-%Y').date()
            except ValueError:
                continue
            data[r[0]][d] = dict(op=num(r[4]), hi=num(r[5]), lo=num(r[6]), cl=num(r[8]),
                                 vol=num(r[10]), to=num(r[11]), dl=num(r[14]))
if not data:
    print('no data'); sys.exit(1)

# ---- Nifty proxy: NIFTYBEES close above its 50 EMA
nifty_up = {}
nb = data.get('NIFTYBEES')
if nb:
    nds = sorted(d for d in nb if nb[d]['cl'] is not None)
    ncl = [nb[d]['cl'] for d in nds]
    ne50 = ema(ncl, 50)
    for d, c, e in zip(nds, ncl, ne50):
        nifty_up[d] = c > e

trades = []
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')):
        continue
    ds = sorted(d for d in byd if all(byd[d][k] is not None for k in ('op', 'hi', 'lo', 'cl', 'vol', 'to')))
    n = len(ds)
    if n < 70:
        continue
    bars = [byd[d] for d in ds]
    op = [b['op'] for b in bars]; hi = [b['hi'] for b in bars]; lo = [b['lo'] for b in bars]
    cl = [b['cl'] for b in bars]; vol = [b['vol'] for b in bars]; to = [b['to'] / 100.0 for b in bars]
    dl = [b['dl'] for b in bars]
    e20 = ema(cl, 20); e50 = ema(cl, 50)
    rs = rsi_series(cl); adx = adx_series(hi, lo, cl); mh = macd_hist_series(cl)
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]   # split/bonus
    last_bad = -10 ** 9
    bp = 0
    for i in range(60, n - HOLD_DAYS - ENTRY_WINDOW):
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]
            bp += 1
        if last_bad > i - 90:
            continue
        r = rs[i]
        if r is None or adx[i] is None:
            continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5 or cl[i] > 6000:
            continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / cl[i] < 0.004:
            continue
        chg = (cl[i] / cl[i - 1] - 1) * 100
        upper = (cl[i] >= hi[i] - 0.01) and any(a <= chg <= b for a, b in [(4.8, 5.05), (9.8, 10.05), (19.8, 20.05)])
        if upper:
            continue
        prevhi = max(hi[i - 20:i])
        vx = vol[i] / (sum(vol[i - 20:i]) / 20.0)
        setup = ''
        if cl[i] > prevhi and vx >= 1.5 and cl[i] > e50[i] and chg > 0 and e20[i] > e50[i]:
            setup = 'BREAKOUT'
        elif (e20[i] * 0.985 <= cl[i] <= e20[i] * 1.03 and e20[i] > e50[i] and cl[i] > e50[i]
              and 38 <= r <= 52 and e50[i] > e50[i - 5]):
            setup = 'PULLBACK'
        if not setup:
            continue
        dprev = [x for x in dl[i - 20:i] if x is not None]
        del_a = sum(dprev) / len(dprev) if dprev else None
        low_del = dl[i] is not None and del_a is not None and del_a > 0 and dl[i] < 0.6 * del_a
        extended = r > 70 or chg > 8
        # ---- entry: GTT-like trigger just above signal-day high, valid ENTRY_WINDOW days
        trig = hi[i] * 1.001
        fill = None
        for j in range(i + 1, i + 1 + ENTRY_WINDOW):
            if hi[j] >= trig:
                if op[j] > trig * GAP_SKIP:
                    fill = 'GAP'
                else:
                    fill = j
                break
        if fill is None or fill == 'GAP':
            continue
        j = fill
        entry = max(op[j], trig)
        risk = ATR_STOP * atr
        stop = entry - risk
        target = entry + RR * risk
        exit_p = None
        for k in range(j, min(j + HOLD_DAYS, n)):
            if op[k] <= stop and k > j:
                exit_p = op[k]; break
            if lo[k] <= stop:
                exit_p = stop; break
            if hi[k] >= target:
                exit_p = target; break
        if exit_p is None:
            exit_p = cl[min(j + HOLD_DAYS - 1, n - 1)]
        r_mult = (exit_p - entry) / risk - (COST_PCT / 100.0 * entry) / risk
        trades.append(dict(sym=sym, date=ds[i].isoformat(), setup=setup, entry=round(entry, 2),
                           stop=round(stop, 2), target=round(target, 2), exit=round(exit_p, 2),
                           R=round(r_mult, 3), adx=round(adx[i], 1), macd_h=round(mh[i], 3),
                           low_del=int(low_del), extended=int(extended),
                           nifty_up=(1 if nifty_up.get(ds[i]) else (0 if ds[i] in nifty_up else -1))))

with open(os.path.join(out_dir, 'backtest_trades.csv'), 'w', newline='', encoding='utf-8') as h:
    cols = ['sym', 'date', 'setup', 'entry', 'stop', 'target', 'exit', 'R', 'adx', 'macd_h', 'low_del', 'extended', 'nifty_up']
    w = csv.DictWriter(h, fieldnames=cols)
    w.writeheader()
    w.writerows(trades)

def stats(sel):
    n = len(sel)
    if n == 0:
        return 'n=0'
    rs_ = [t['R'] for t in sel]
    wins = sum(1 for x in rs_ if x > 0)
    gp = sum(x for x in rs_ if x > 0)
    gl = -sum(x for x in rs_ if x < 0)
    pf = (gp / gl) if gl > 0 else float('inf')
    return 'n=%d  win%%=%.0f  avgR=%.2f  totalR=%.1f  profit_factor=%.2f' % (
        n, 100.0 * wins / n, sum(rs_) / n, sum(rs_), pf)


filters = [
    ('ALL signals', lambda t: True),
    ('ADX >= 20', lambda t: t['adx'] >= 20),
    ('ADX >= 25', lambda t: t['adx'] >= 25),
    ('MACD_H > 0', lambda t: t['macd_h'] > 0),
    ('ADX>=20 and MACD_H>0', lambda t: t['adx'] >= 20 and t['macd_h'] > 0),
    ('Nifty(NIFTYBEES) above 50EMA', lambda t: t['nifty_up'] == 1),
    ('Nifty below 50EMA', lambda t: t['nifty_up'] == 0),
    ('No LOW_DELIV/EXTENDED flag', lambda t: not t['low_del'] and not t['extended']),
    ('Flagged LOW_DELIV or EXTENDED', lambda t: t['low_del'] or t['extended']),
    ('No flags + ADX>=20 + MACD_H>0 + Nifty up',
     lambda t: not t['low_del'] and not t['extended'] and t['adx'] >= 20 and t['macd_h'] > 0 and t['nifty_up'] == 1),
]
alldates = sorted({d for s in data.values() for d in s})
lines = ['BACKTEST SUMMARY (generated %s)' % datetime.date.today().isoformat(),
         'Data: %s to %s (%d trading dates), symbols: %d' % (alldates[0], alldates[-1], len(alldates), len(data)),
         'Rules: signal as in screen.py; entry = GTT above signal-day high (valid %d days, skip if open >1.5%% above trigger);'
         % ENTRY_WINDOW,
         'stop = entry - %.1f x ATR14; target = %.1f x risk; max hold %d days; same-day stop+target counts as stop;'
         % (ATR_STOP, RR, HOLD_DAYS),
         'cost %.2f%% round trip deducted. Each signal treated independently (no capital limit). R = profit / risk.'
         % COST_PCT, '']
for label, setup in (('ALL SETUPS', None), ('BREAKOUT only', 'BREAKOUT'), ('PULLBACK only', 'PULLBACK')):
    lines.append('== %s ==' % label)
    base = [t for t in trades if setup is None or t['setup'] == setup]
    for name, fn in filters:
        lines.append('%-45s %s' % (name, stats([t for t in base if fn(t)])))
    lines.append('')
lines.append('Caution: past results do not guarantee future results; small n means unreliable numbers.')
with open(os.path.join(out_dir, 'backtest_summary.txt'), 'w', encoding='utf-8') as h:
    h.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
