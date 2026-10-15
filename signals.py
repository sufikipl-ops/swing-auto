# Signal discovery: 10 signal families x 4 exit rules, validated on 3 time slices.
# usage: python signals.py <bhav_folder> <output_folder>
import csv, glob, os, sys, datetime, collections, bisect

bhav_dir = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

COST_PCT = 0.25
ENTRY_WINDOW = 4
GAP_SKIP = 1.015
MAX_HOLD = 10
START = 100
MIN_N = 200
# (entry, stop ATR multiple, RR (99 = no target), hold days)
CONFIGS = [('OPEN', 2.0, 99, 3), ('OPEN', 2.0, 99, 5), ('OPEN', 3.0, 99, 10), ('TRIG', 2.0, 2.0, 5)]


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


class C(object):
    __slots__ = ('sym', 'date', 'i', 'n', 'op', 'hi', 'lo', 'cl', 'atr', 'low5', 'e20', 'e50', 'e100', 'rsi',
                 'ret3', 'ret20', 'ret60', 'hi100', 'nr7', 'vx', 'cpos', 'chg', 'pr20', 'rs60')


# ---- load
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
                                 vol=num(r[10]), to=num(r[11]))
if not data:
    print('no data'); sys.exit(1)

# ---- nifty proxy: 60-day return by date, and trend flag
nret60 = {}
nup = {}
nb = data.get('NIFTYBEES', {})
nds = sorted(d for d in nb if nb[d]['cl'] is not None)
if len(nds) > 70:
    ncl = [nb[d]['cl'] for d in nds]
    n50 = ema(ncl, 50)
    for k in range(60, len(nds)):
        nret60[nds[k]] = ncl[k] / ncl[k - 60] - 1
        nup[nds[k]] = ncl[k] > n50[k]
      # ---- candidates (liquid universe), features per symbol-day
cands = []
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')):
        continue
    ds = sorted(d for d in byd if all(byd[d][k] is not None for k in ('op', 'hi', 'lo', 'cl', 'vol', 'to')))
    n = len(ds)
    if n < START + 20:
        continue
    bars = [byd[d] for d in ds]
    op = [b['op'] for b in bars]; hi = [b['hi'] for b in bars]; lo = [b['lo'] for b in bars]
    cl = [b['cl'] for b in bars]; vol = [b['vol'] for b in bars]; to = [b['to'] / 100.0 for b in bars]
    e20 = ema(cl, 20); e50 = ema(cl, 50); e100 = ema(cl, 100)
    rs = rsi_series(cl)
    rng = [hi[i] - lo[i] for i in range(n)]
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    last_bad = -10 ** 9
    bp = 0
    for i in range(START, n - ENTRY_WINDOW - MAX_HOLD - 1):
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]
            bp += 1
        if last_bad > i - 90 or rs[i] is None:
            continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5 or cl[i] > 6000:
            continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / cl[i] < 0.004:
            continue
        chg = (cl[i] / cl[i - 1] - 1) * 100
        if (cl[i] >= hi[i] - 0.01) and any(a <= chg <= b for a, b in [(4.8, 5.05), (9.8, 10.05), (19.8, 20.05)]):
            continue
        c = C()
        c.sym, c.date, c.i, c.n = sym, ds[i], i, n
        c.op, c.hi, c.lo, c.cl, c.atr = op, hi, lo, cl, atr
        c.low5 = min(lo[i - 4:i + 1])
        c.e20, c.e50, c.e100, c.rsi = e20[i], e50[i], e100[i], rs[i]
        c.ret3 = cl[i] / cl[i - 3] - 1
        c.ret20 = cl[i] / cl[i - 20] - 1
        c.ret60 = cl[i] / cl[i - 60] - 1
        c.hi100 = max(hi[i - 100:i])
        c.nr7 = rng[i] <= min(rng[i - 6:i + 1]) and rng[i] > 0
        c.vx = vol[i] / (sum(vol[i - 20:i]) / 20.0)
        c.cpos = (cl[i] - lo[i]) / rng[i] if rng[i] > 0 else 0.5
        c.chg = chg
        c.rs60 = c.ret60 - nret60.get(ds[i], 0.0)
        c.pr20 = 0.0
        cands.append(c)
print('candidates:', len(cands))
if not cands:
    sys.exit(1)
# cross-sectional percentile of 20-day return per date
bydate = collections.defaultdict(list)
for c in cands:
    bydate[c.date].append(c.ret20)
for k in bydate:
    bydate[k].sort()
for c in cands:
    arr = bydate[c.date]
    c.pr20 = bisect.bisect_left(arr, c.ret20) / float(len(arr))
alld = sorted(set(c.date for c in cands))
cut1, cut2 = alld[len(alld) // 3], alld[2 * len(alld) // 3]
print('dates', alld[0], 'to', alld[-1], '| slices end', cut1, cut2)
def simulate(s, entry_mode, stop_mult, rr, hold):
    op, hi, lo, cl, i, n, atr = s.op, s.hi, s.lo, s.cl, s.i, s.n, s.atr
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
    risk = stop_mult * atr
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
    r_ = (exit_p - entry) / risk - (COST_PCT / 100.0 * entry) / risk
    pct = (exit_p / entry - 1) * 100 - COST_PCT
    return r_, pct


def agg(vals):
    n = len(vals)
    if n == 0:
        return 0, 0.0, 0.0
    gp = sum(v for v in vals if v > 0)
    gl = -sum(v for v in vals if v < 0)
    return n, sum(vals) / n, (gp / gl if gl > 0 else 9.99)


SIGNALS = [
    ('BASE (every 5th day)', lambda c: c.i % 5 == 0),
    ('MOM_TOP10', lambda c: c.pr20 >= 0.9 and c.cl[c.i] > c.e50 and c.e20 > c.e50),
    ('NEW_100D_HIGH', lambda c: c.cl[c.i] > c.hi100 and c.vx >= 1.5 and c.chg > 0),
    ('RS_LEADER', lambda c: c.rs60 > 0.10 and c.cl[c.i] >= 0.93 * c.hi100 and c.cl[c.i] > c.e20),
    ('NR7_UPTREND', lambda c: c.nr7 and c.cl[c.i] > c.e50 and c.e20 > c.e50),
    ('DIP_IN_UPTREND', lambda c: c.ret3 <= -0.05 and c.cl[c.i] > c.e50 and c.e20 > c.e50),
    ('OVERSOLD_BOUNCE', lambda c: c.rsi < 32 and c.cl[c.i] > c.e100 and c.chg > 0),
    ('THRUST_CANDLE', lambda c: c.chg >= 4 and c.cpos >= 0.9 and c.vx >= 2 and c.cl[c.i] > c.e50),
    ('COMBO_A mom+nearHigh+vol', lambda c: c.pr20 >= 0.9 and c.cl[c.i] >= 0.95 * c.hi100 and c.vx >= 1.2
        and c.e20 > c.e50),
    ('COMBO_B thrust+mom', lambda c: c.chg >= 3 and c.cpos >= 0.85 and c.vx >= 1.5 and c.pr20 >= 0.8
        and c.cl[c.i] > c.e50),
    ('COMBO_C RS+nearHigh+nifty up', lambda c: c.rs60 > 0.05 and c.cl[c.i] >= 0.95 * c.hi100
        and c.e20 > c.e50 and nup.get(c.date, False)),
]

rows = []
for cfg in CONFIGS:
    em, sm, rr, hold = cfg
    sim = {}
    for c in cands:
        res = simulate(c, em, sm, rr, hold)
        if res is not None:
            sim[id(c)] = res
    for name, fn in SIGNALS:
        sl = ([], [], [])
        allr, allp = [], []
        for c in cands:
            res = sim.get(id(c))
            if res is None or not fn(c):
                continue
            allr.append(res[0]); allp.append(res[1])
            sl[0 if c.date <= cut1 else (1 if c.date <= cut2 else 2)].append(res[0])
        n, avg, pf = agg(allr)
        a = [agg(x) for x in sl]
        win = round(100.0 * sum(1 for v in allr if v > 0) / n) if n else 0
        rows.append(dict(signal=name, entry=em, stop=sm, rr=rr, hold=hold, n=n, win=win, avgR=round(avg, 3),
                         pf=round(pf, 2), avgPct=round(sum(allp) / n, 2) if n else 0,
                         T1=round(a[0][1], 3), T2=round(a[1][1], 3), T3=round(a[2][1], 3),
                         nT1=a[0][0], nT2=a[1][0], nT3=a[2][0]))

with open(os.path.join(out_dir, 'signals_results.csv'), 'w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

ndays = len(alld)
lines = ['SIGNAL DISCOVERY (generated %s)' % datetime.date.today().isoformat(),
         'Dates %s to %s (%d trading days). Slices T1/T2/T3 = thirds of time (ends %s, %s).' % (
             alld[0], alld[-1], ndays, cut1, cut2),
         'Exit = (entry, stop ATR x, RR [99 = no target], hold days). Cost %.2f%% round trip. avgPct = avg %% per trade '
         'after cost. BASE = random stock every 5th day (market drift reference).' % COST_PCT, '']
hdr = '%-28s %-5s %-4s %-3s %-4s %6s %5s %7s %5s %7s %7s %7s %7s' % (
    'signal', 'entry', 'stop', 'RR', 'hold', 'n', 'win%', 'avgR', 'PF', 'avg%', 'T1', 'T2', 'T3')
for cfg in CONFIGS:
    lines.append('== exit %s ==' % (cfg,))
    lines.append(hdr)
    for r in rows:
        if (r['entry'], r['stop'], r['rr'], r['hold']) == cfg:
            lines.append('%-28s %-5s %-4s %-3s %-4s %6d %5d %7.3f %5.2f %7.2f %7.3f %7.3f %7.3f' % (
                r['signal'], r['entry'], r['stop'], r['rr'], r['hold'], r['n'], r['win'], r['avgR'], r['pf'],
                r['avgPct'], r['T1'], r['T2'], r['T3']))
    lines.append('')
good = [r for r in rows if r['n'] >= MIN_N and r['T1'] > 0 and r['T2'] > 0 and r['T3'] > 0
        and not r['signal'].startswith('BASE')]
lines.append('Rows with n >= %d and avgR > 0 in ALL 3 slices: %d of %d' % (
    MIN_N, len(good), sum(1 for r in rows if r['n'] >= MIN_N)))
for r in sorted(good, key=lambda x: -x['avgR'])[:20]:
    lines.append('  %s | %s %s %s %s | n=%d win=%d%% avgR=%.3f avg%%=%.2f T=%.3f/%.3f/%.3f' % (
        r['signal'], r['entry'], r['stop'], r['rr'], r['hold'], r['n'], r['win'], r['avgR'], r['avgPct'],
        r['T1'], r['T2'], r['T3']))
lines.append('Caution: 11 signals x 4 exits tried; some positive rows can be luck. Past results do not guarantee '
             'future results.')
with open(os.path.join(out_dir, 'signals_summary.txt'), 'w', encoding='utf-8') as h:
    h.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
