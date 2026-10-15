# Filter test: market-trend + quality filters on a few fixed exit rules.
# usage: python filters.py <bhav_folder> <output_folder>
# Writes: filters_summary.txt and filters_results.csv in <output_folder>
import csv, glob, os, sys, datetime, collections

bhav_dir = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

COST_PCT = 0.25
ENTRY_WINDOW = 4
GAP_SKIP = 1.015
MAX_HOLD = 10
MIN_N = 150
# fixed exit rules (entry, stop, rr, hold)
CONFIGS = [('TRIG', 'LOW5', 1.5, 10), ('TRIG', 3.0, 1.0, 10), ('OPEN', 3.0, 1.5, 5)]


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


def wilder(vals, n=14):
    s = sum(vals[:n])
    out = [s]
    for v in vals[n:]:
        s = s - s / n + v
        out.append(s)
    return out


def adx_series(hi, lo, cl):
    n = 14
    res = [None] * len(cl)
    if len(cl) < 2 * n + 2:
        return res
    pdm, mdm, trl = [], [], []
    for i in range(1, len(cl)):
        up = hi[i] - hi[i - 1]
        dn = lo[i - 1] - lo[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
        trl.append(max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])))
    st, sp, sm = wilder(trl, n), wilder(pdm, n), wilder(mdm, n)
    dx = []
    for a, b, c in zip(st, sp, sm):
        p, m = (100.0 * b / a, 100.0 * c / a) if a else (0.0, 0.0)
        dx.append(0.0 if p + m == 0 else 100.0 * abs(p - m) / (p + m))
    adx = sum(dx[:n]) / n
    res[2 * n - 1 + 0] = adx            # dx index n-1 -> bar 2n-1
    for m in range(n, len(dx)):
        adx = (adx * (n - 1) + dx[m]) / n
        res[n + m] = adx
    return res
  # ---- load all bhavcopy files (EQ only)
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

# ---- market proxy: NIFTYBEES vs its EMAs
nifty = {}
nb = data.get('NIFTYBEES', {})
nds = sorted(d for d in nb if nb[d]['cl'] is not None)
if len(nds) > 60:
    ncl = [nb[d]['cl'] for d in nds]
    n20, n50 = ema(ncl, 20), ema(ncl, 50)
    for k, d in enumerate(nds):
        if k >= 50:
            nifty[d] = (ncl[k] > n50[k], n20[k] > n50[k])

# ---- signals (same setup rules as screen.py) with extra features
signals = []
breadth = collections.defaultdict(lambda: [0, 0])      # date -> [above EMA50, total]
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
    macd = [a - b for a, b in zip(ema(cl, 12), ema(cl, 26))]
    msig = ema(macd, 9)
    rs = rsi_series(cl)
    adx = adx_series(hi, lo, cl)
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    last_bad = -10 ** 9
    bp = 0
    for i in range(60, n - ENTRY_WINDOW - MAX_HOLD - 1):
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]
            bp += 1
        if last_bad > i - 90:
            continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 >= 5:
            breadth[ds[i]][1] += 1
            if cl[i] > e50[i]:
                breadth[ds[i]][0] += 1
        r = rs[i]
        if r is None or to20 < 5 or cl[i] > 6000:
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
        dwin = [x for x in dl[i - 20:i] if x is not None]
        dratio = (dl[i] / (sum(dwin) / len(dwin))) if (dl[i] is not None and dwin and sum(dwin) > 0) else None
        signals.append(dict(setup=setup, date=ds[i], op=op, hi=hi, lo=lo, cl=cl, i=i, n=n,
                            atr=atr, low5=min(lo[i - 4:i + 1]), adx=adx[i], mh=macd[i] - msig[i],
                            dratio=dratio, to20=to20, rsi=r))
print('signals:', len(signals))
if not signals:
    sys.exit(1)
sdates = sorted(s['date'] for s in signals)
mid = sdates[len(sdates) // 2]
def simulate(s, entry_mode, stop_mode, rr, hold):
    op, hi, lo, cl, i, n, atr = s['op'], s['hi'], s['lo'], s['cl'], s['i'], s['n'], s['atr']
    if entry_mode == 'OPEN':
        j = i + 1
        if op[j] > cl[i] * GAP_SKIP:
            return None
        entry = op[j]
    else:
        trig = hi[i] * 1.001
        j = None
        for jj in range(i + 1, i + 1 + ENTRY_WINDOW):
            if hi[jj] >= trig:
                if op[jj] > trig * GAP_SKIP:
                    return None
                j = jj
                break
        if j is None:
            return None
        entry = max(op[j], trig)
    if stop_mode == 'LOW5':
        stop = s['low5']
        risk = entry - stop
        if risk <= 0.3 * atr or risk > 4 * atr:
            return None
    else:
        risk = stop_mode * atr
        stop = entry - risk
    target = entry + rr * risk
    end = min(j + hold, n)
    exit_p = None
    for k in range(j, end):
        if k > j and op[k] <= stop:
            exit_p = op[k]
            break
        if lo[k] <= stop:
            exit_p = stop
            break
        if hi[k] >= target:
            exit_p = target
            break
    if exit_p is None:
        exit_p = cl[end - 1]
    return (exit_p - entry) / risk - (COST_PCT / 100.0 * entry) / risk


def agg(vals):
    n = len(vals)
    if n == 0:
        return 0, 0.0, 0.0
    gp = sum(v for v in vals if v > 0)
    gl = -sum(v for v in vals if v < 0)
    return n, sum(vals) / n, (gp / gl if gl > 0 else 9.99)


def nf(s, k):
    return nifty.get(s['date'], (False, False))[k]


def br(s):
    a, t = breadth.get(s['date'], (0, 0))
    return a / t if t else 0.0


def has(v, lim):
    return v is not None and v > lim


FILTERS = [
    ('NONE', lambda s: True),
    ('NIFTY>EMA50', lambda s: nf(s, 0)),
    ('NIFTY up-trend', lambda s: nf(s, 0) and nf(s, 1)),
    ('BREADTH>50%', lambda s: br(s) > 0.50),
    ('BREADTH>60%', lambda s: br(s) > 0.60),
    ('ADX>25', lambda s: has(s['adx'], 25)),
    ('ADX>30', lambda s: has(s['adx'], 30)),
    ('MACD_H>0', lambda s: s['mh'] > 0),
    ('DELIV>=1.0x', lambda s: has(s['dratio'], 1.0)),
    ('TURN20>=20cr', lambda s: s['to20'] >= 20),
    ('NIFTY+ADX25', lambda s: nf(s, 0) and has(s['adx'], 25)),
    ('BREADTH50+ADX25+MACD', lambda s: br(s) > 0.5 and has(s['adx'], 25) and s['mh'] > 0),
    ('BREADTH60+ADX25+DELIV', lambda s: br(s) > 0.6 and has(s['adx'], 25) and has(s['dratio'], 1.0)),
    ('STRICT (all)', lambda s: nf(s, 0) and br(s) > 0.5 and has(s['adx'], 25) and s['mh'] > 0
        and has(s['dratio'], 1.0) and s['to20'] >= 20),
]

rows = []
for cfg in CONFIGS:
    em, sm, rr, hold = cfg
    sim = [(s, simulate(s, em, sm, rr, hold)) for s in signals]
    sim = [(s, r_) for s, r_ in sim if r_ is not None]
    for fname, fn in FILTERS:
        buckets = {k: ([], [], []) for k in ('ALL', 'BREAKOUT', 'PULLBACK')}
        for s, r_ in sim:
            if not fn(s):
                continue
            h_ = 1 if s['date'] <= mid else 2
            for key in ('ALL', s['setup']):
                buckets[key][0].append(r_)
                buckets[key][h_].append(r_)
        for key, (allv, h1, h2) in buckets.items():
            n, avg, pf = agg(allv)
            n1, a1, _ = agg(h1)
            n2, a2, _ = agg(h2)
            win = round(100.0 * sum(1 for v in allv if v > 0) / n) if n else 0
            rows.append(dict(entry=em, stop=sm, rr=rr, hold=hold, filt=fname, setup=key, n=n, win=win,
                             avgR=round(avg, 3), pf=round(pf, 2), avgR_H1=round(a1, 3), avgR_H2=round(a2, 3),
                             n_H1=n1, n_H2=n2))

with open(os.path.join(out_dir, 'filters_results.csv'), 'w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

lines = ['FILTER TEST (generated %s)' % datetime.date.today().isoformat(),
         'Signals: %d from %s to %s; H1 = up to %s, H2 = after.' % (len(signals), sdates[0], sdates[-1], mid),
         'Exit rules fixed: (entry, stop, RR, hold). Cost %.2f%% round trip. Rows with n < %d are marked (small).' % (
             COST_PCT, MIN_N), '']
hdr = '%-22s %-9s %6s %5s %7s %5s %8s %8s %6s %6s' % (
    'filter', 'setup', 'n', 'win%', 'avgR', 'PF', 'avgR_H1', 'avgR_H2', 'n_H1', 'n_H2')
for cfg in CONFIGS:
    for key in ('ALL', 'BREAKOUT', 'PULLBACK'):
        lines.append('== exit %s | %s ==' % (cfg, key))
        lines.append(hdr)
        for r in rows:
            if (r['entry'], r['stop'], r['rr'], r['hold']) == cfg and r['setup'] == key:
                lines.append('%-22s %-9s %6d %5d %7.3f %5.2f %8.3f %8.3f %6d %6d%s' % (
                    r['filt'], r['setup'], r['n'], r['win'], r['avgR'], r['pf'], r['avgR_H1'], r['avgR_H2'],
                    r['n_H1'], r['n_H2'], '  (small)' if r['n'] < MIN_N else ''))
        lines.append('')
good = [r for r in rows if r['n'] >= MIN_N and r['avgR'] > 0 and r['avgR_H1'] > 0 and r['avgR_H2'] > 0]
lines.append('Rows with n >= %d and avgR > 0 in BOTH halves: %d of %d' % (
    MIN_N, len(good), sum(1 for r in rows if r['n'] >= MIN_N)))
for r in sorted(good, key=lambda x: -x['avgR'])[:15]:
    lines.append('  %s %s %s %s | %s | %s | n=%d avgR=%.3f H1=%.3f H2=%.3f' % (
        r['entry'], r['stop'], r['rr'], r['hold'], r['filt'], r['setup'], r['n'], r['avgR'], r['avgR_H1'], r['avgR_H2']))
lines.append('Caution: 14 filters x 3 exits x 3 groups were tried; a few positive rows can be luck. '
             'Past results do not guarantee future results.')
with open(os.path.join(out_dir, 'filters_summary.txt'), 'w', encoding='utf-8') as h:
    h.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
