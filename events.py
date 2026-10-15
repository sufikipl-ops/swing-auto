# Event-reaction test: gap-up + volume spike days (proxy for results/news), validated on 3 time slices.
# usage: python events.py <bhav_folder> <output_folder>
# Writes events_summary.txt and events_results.csv. Also uses each stock's OWN past event reactions.
import csv, glob, os, sys, datetime, collections

bhav_dir = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

COST_PCT = 0.25
ENTRY_WINDOW = 4
GAP_SKIP = 1.015
MAX_HOLD = 10
START = 60
MIN_N = 100
# (entry, stop [ATR multiple or LOWDAY = low of event day], RR (99 = no target), hold days)
CONFIGS = [('TRIG', 'LOWDAY', 1.5, 5), ('TRIG', 2.0, 99, 5), ('OPEN', 2.0, 99, 3), ('OPEN', 'LOWDAY', 99, 5)]


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


class C(object):
    __slots__ = ('sym', 'date', 'i', 'n', 'op', 'hi', 'lo', 'cl', 'atr', 'gap', 'vx', 'cpos', 'chg', 'hist',
                 'nhist', 'dlow')


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
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    last_bad = -10 ** 9
    bp = 0
    past = []                       # (event index) of this stock's earlier event days
    for i in range(START, n - ENTRY_WINDOW - MAX_HOLD - 1):
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]
            bp += 1
        if last_bad > i - 90:
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
        gap = (op[i] / cl[i - 1] - 1) * 100
        vx = vol[i] / (sum(vol[i - 20:i]) / 20.0)
        rng = hi[i] - lo[i]
        cpos = (cl[i] - lo[i]) / rng if rng > 0 else 0.5
        is_event = gap >= 3.0 and vx >= 3.0
        if not (is_event or i % 5 == 0):
            continue
        reacts = [cl[e + 3] / cl[e] - 1 for e in past if e + 3 <= i]
        c = C()
        c.sym, c.date, c.i, c.n = sym, ds[i], i, n
        c.op, c.hi, c.lo, c.cl, c.atr = op, hi, lo, cl, atr
        c.gap, c.vx, c.cpos, c.chg, c.dlow = gap, vx, cpos, chg, lo[i]
        c.hist = (sum(reacts) / len(reacts)) if reacts else None
        c.nhist = len(reacts)
        cands.append(c)
        if is_event:
            past.append(i)
print('candidates:', len(cands))
if not cands:
    sys.exit(1)
alld = sorted(set(c.date for c in cands))
cut1, cut2 = alld[len(alld) // 3], alld[2 * len(alld) // 3]
print('dates', alld[0], 'to', alld[-1], '| slices end', cut1, cut2)

def simulate(s, entry_mode, stop_mode, rr, hold):
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
    if stop_mode == 'LOWDAY':
        stop = s.dlow
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


def ev(c, g=3.0, v=3.0):
    return c.gap >= g and c.vx >= v


SIGNALS = [
    ('BASE (every 5th day)', lambda c: c.i % 5 == 0),
    ('EVENT gap>=3 vol>=3x', lambda c: ev(c)),
    ('EVENT + closed up (c>o)', lambda c: ev(c) and c.cl[c.i] > c.op[c.i]),
    ('EVENT + close in top 30%', lambda c: ev(c) and c.cpos >= 0.7),
    ('EVENT big gap>=5 vol>=4x', lambda c: ev(c, 5.0, 4.0) and c.cpos >= 0.6),
    ('EVENT + stock history>0', lambda c: ev(c) and c.hist is not None and c.hist > 0 and c.nhist >= 2),
    ('EVENT + hist>0 + top 30%', lambda c: ev(c) and c.cpos >= 0.7 and c.hist is not None and c.hist > 0
        and c.nhist >= 2),
    ('EVENT + stock history<0', lambda c: ev(c) and c.hist is not None and c.hist < 0 and c.nhist >= 2),
    ('EVENT gap-fade (c<o)', lambda c: ev(c) and c.cl[c.i] < c.op[c.i]),
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

with open(os.path.join(out_dir, 'events_results.csv'), 'w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

# raw next-day behaviour of event days (no stops): avg % move from event close over 1/3/5 days vs base
def fwd(sel, k):
    v = [(c.cl[c.i + k] / c.cl[c.i] - 1) * 100 for c in sel if c.i + k < c.n]
    return (sum(v) / len(v), len(v)) if v else (0.0, 0)


lines = ['EVENT-REACTION TEST (generated %s)' % datetime.date.today().isoformat(),
         'Dates %s to %s. Event day = gap-up >= 3%% and volume >= 3x 20-day avg (proxy for results/news). '
         'T1/T2/T3 = thirds of time (ends %s, %s).' % (alld[0], alld[-1], cut1, cut2),
         'Exit = (entry, stop [LOWDAY = event-day low], RR [99 = none], hold days). Cost %.2f%% round trip. '
         'hist = this stock\'s own avg 3-day return after its earlier event days.' % COST_PCT, '']
base = [c for c in cands if c.i % 5 == 0]
evs = [c for c in cands if ev(c)]
lines.append('Raw drift after close of day (avg % move, no stops):')
for k in (1, 3, 5):
    b, nb = fwd(base, k)
    e, ne = fwd(evs, k)
    lines.append('  +%dd: BASE %.2f%% (n=%d) | EVENT days %.2f%% (n=%d)' % (k, b, nb, e, ne))
lines.append('')
hdr = '%-28s %-5s %-7s %-3s %-4s %6s %5s %7s %5s %7s %7s %7s %7s' % (
    'signal', 'entry', 'stop', 'RR', 'hold', 'n', 'win%', 'avgR', 'PF', 'avg%', 'T1', 'T2', 'T3')
for cfg in CONFIGS:
    lines.append('== exit %s ==' % (cfg,))
    lines.append(hdr)
    for r in rows:
        if (r['entry'], r['stop'], r['rr'], r['hold']) == cfg:
            lines.append('%-28s %-5s %-7s %-3s %-4s %6d %5d %7.3f %5.2f %7.2f %7.3f %7.3f %7.3f' % (
                r['signal'], r['entry'], r['stop'], r['rr'], r['hold'], r['n'], r['win'], r['avgR'], r['pf'],
                r['avgPct'], r['T1'], r['T2'], r['T3']))
    lines.append('')
good = [r for r in rows if r['n'] >= MIN_N and r['T1'] > 0 and r['T2'] > 0 and r['T3'] > 0
        and not r['signal'].startswith('BASE')]
lines.append('Rows with n >= %d and avgR > 0 in ALL 3 slices: %d of %d' % (
    MIN_N, len(good), sum(1 for r in rows if r['n'] >= MIN_N)))
for r in sorted(good, key=lambda x: -x['avgR'])[:15]:
    lines.append('  %s | %s %s %s %s | n=%d win=%d%% avgR=%.3f avg%%=%.2f T=%.3f/%.3f/%.3f' % (
        r['signal'], r['entry'], r['stop'], r['rr'], r['hold'], r['n'], r['win'], r['avgR'], r['avgPct'],
        r['T1'], r['T2'], r['T3']))
lines.append('Caution: 9 signals x 4 exits tried; small samples can be luck. Past results do not guarantee future results.')
with open(os.path.join(out_dir, 'events_summary.txt'), 'w', encoding='utf-8') as h:
    h.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
