# Sweep of entry / stop / target / hold rules on NSE bhavcopy history.
# usage: python sweep.py <bhav_folder> <output_folder>
# Writes: sweep_summary.txt and sweep_results.csv in <output_folder>
import csv, glob, os, sys, datetime, collections

bhav_dir = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

COST_PCT = 0.25
ENTRY_WINDOW = 4
GAP_SKIP = 1.015
MAX_HOLD = 10
MIN_N = 300

ENTRY_MODES = ['OPEN', 'TRIG']                 # next-day open  /  GTT above signal-day high
STOP_MODES = [0.8, 1.0, 1.5, 2.0, 3.0, 'LOW5']   # ATR multiples, or lowest low of last 5 days
RRS = [1.0, 1.5, 2.0, 3.0]
HOLDS = [5, 10]


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
    return out# ---- load all bhavcopy files (EQ only)
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

# ---- signals (same rules as screen.py), stored once
signals = []
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
    e20 = ema(cl, 20); e50 = ema(cl, 50)
    rs = rsi_series(cl)
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
        r = rs[i]
        if r is None:
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
        signals.append(dict(setup=setup, date=ds[i], op=op, hi=hi, lo=lo, cl=cl, i=i, n=n,
                            atr=atr, low5=min(lo[i - 4:i + 1])))
print('signals:', len(signals))
if not signals:
    sys.exit(1)
sdates = sorted(s['date'] for s in signals)
mid = sdates[len(sdates) // 2]def simulate(s, entry_mode, stop_mode, rr, hold):
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


rows = []
for em in ENTRY_MODES:
    for sm in STOP_MODES:
        for rr in RRS:
            for hold in HOLDS:
                buckets = {k: [] for k in ('ALL', 'BREAKOUT', 'PULLBACK')}
                halves = {k: ([], []) for k in buckets}
                for s in signals:
                    r_ = simulate(s, em, sm, rr, hold)
                    if r_ is None:
                        continue
                    h_ = 0 if s['date'] <= mid else 1
                    for key in ('ALL', s['setup']):
                        buckets[key].append(r_)
                        halves[key][h_].append(r_)
                for key in buckets:
                    n, avg, pf = agg(buckets[key])
                    n1, a1, _ = agg(halves[key][0])
                    n2, a2, _ = agg(halves[key][1])
                    wins = sum(1 for v in buckets[key] if v > 0)
                    rows.append(dict(setup=key, entry=em, stop=sm, rr=rr, hold=hold, n=n,
                                     win=round(100.0 * wins / n) if n else 0, avgR=round(avg, 3), pf=round(pf, 2),
                                     avgR_H1=round(a1, 3), avgR_H2=round(a2, 3), n_H1=n1, n_H2=n2))

with open(os.path.join(out_dir, 'sweep_results.csv'), 'w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

lines = ['SWEEP SUMMARY (generated %s)' % datetime.date.today().isoformat(),
         'Signals: %d from %s to %s; first half = signals up to %s, second half = after.' % (
             len(signals), sdates[0], sdates[-1], mid),
         'Entry OPEN = next-day open (skip if >1.5% above signal close); TRIG = GTT above signal-day high, 4-day window.',
         'Stop = ATR14 multiple or LOW5; target = RR x risk; hold in days; same-bar stop+target counts as stop;',
         'cost %.2f%% round trip. Min trades per row: %d. R = profit / risk.' % (COST_PCT, MIN_N), '']
hdr = '%-9s %-5s %-5s %-4s %-5s %6s %5s %7s %5s %8s %8s' % (
    'setup', 'entry', 'stop', 'RR', 'hold', 'n', 'win%', 'avgR', 'PF', 'avgR_H1', 'avgR_H2')


def fmt(r):
    return '%-9s %-5s %-5s %-4s %-5s %6d %5d %7.3f %5.2f %8.3f %8.3f' % (
        r['setup'], r['entry'], r['stop'], r['rr'], r['hold'], r['n'], r['win'], r['avgR'], r['pf'],
        r['avgR_H1'], r['avgR_H2'])


for key in ('ALL', 'BREAKOUT', 'PULLBACK'):
    sel = [r for r in rows if r['setup'] == key and r['n'] >= MIN_N]
    lines.append('== %s: top 12 combos by avgR (n >= %d) ==' % (key, MIN_N))
    lines.append(hdr)
    for r in sorted(sel, key=lambda x: -x['avgR'])[:12]:
        lines.append(fmt(r))
    both = [r for r in sel if r['avgR_H1'] > 0 and r['avgR_H2'] > 0]
    lines.append('Combos with avgR > 0 in BOTH halves: %d of %d' % (len(both), len(sel)))
    lines.append('Combos with avgR > 0 overall: %d of %d' % (sum(1 for r in sel if r['avgR'] > 0), len(sel)))
    base = [r for r in sel if r['entry'] == 'TRIG' and r['stop'] == 1.5 and r['rr'] == 2.0 and r['hold'] == 5]
    if base:
        lines.append('Earlier backtest rules (TRIG, 1.5 ATR, RR 2, hold 5):')
        lines.append(fmt(base[0]))
    lines.append('')
lines.append('Caution: many combos were tried, so the best rows can look good by luck. Trust only combos that are '
             'positive in BOTH halves with large n. Past results do not guarantee future results.')
with open(os.path.join(out_dir, 'sweep_summary.txt'), 'w', encoding='utf-8') as h:
    h.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
