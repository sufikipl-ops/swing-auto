# "Liquidity sweep" idea (equal-lows / stop-hunt): price dips BELOW the prior N-day low (where stop-losses sit) but CLOSES back above it.
# Long-only test: buy next day open. usage: python sweep_study.py <bhav_folder> <out_folder> -> sweep_summary.txt + sweep_results.csv
# Event day i: lo[i] < L (= lowest low of previous 20 days) and close[i] > L.   EQL = the old low was touched >= 2 times (equal lows).
# Exits: A = stop 1.5 ATR / target 1.5 ATR / 5 days.  B = stop 2 ATR, hold 5 days (close).  C = STRUCTURAL stop just below the sweep low
# (lo[i] - 0.1 ATR, risk clamp 0.5-2.5 ATR), target 2R, 5 days.  Cost 0.25%, skip open gap > +1.5% / < -3%. R = profit / risk.
import csv, glob, os, sys, datetime, collections

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
COST = 0.25 / 100.0
HOLD = 5
TRAIN_END = 2024


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


def ema(v, span):
    a = 2.0 / (span + 1); e = v[0]; out = [e]
    for x in v[1:]:
        e = a * x + (1 - a) * e; out.append(e)
    return out


data = collections.defaultdict(dict)
files = sorted(glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv')))
for f in files:
    with open(f, newline='', encoding='utf-8', errors='ignore') as h:
        rd = csv.reader(h); next(rd, None)
        for r in rd:
            if len(r) < 15 or r[1].strip() != 'EQ': continue
            try:
                d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
            except ValueError:
                continue
            t = tuple(num(r[k]) for k in (4, 5, 6, 8, 10, 11))
            if None in t: continue
            data[r[0].strip()][d] = t
if not data:
    print('no data'); sys.exit(1)
alldates = sorted({d for v in data.values() for d in v})
print('files', len(files), 'symbols', len(data), 'dates', alldates[0], alldates[-1], len(alldates))


def walk(op, hi, lo, cl, j, n, entry, stop, target):
    end = min(j + HOLD, n)
    if end - j < HOLD: return None
    for k in range(j, end):
        if k > j and op[k] <= stop: return op[k]
        if lo[k] <= stop: return stop
        if target is not None and hi[k] >= target: return target
    return cl[end - 1]


def trade(op, hi, lo, cl, i, n, atr, kind, sweep_low):
    j = i + 1
    if j >= n: return None
    if op[j] > cl[i] * 1.015 or op[j] < cl[i] * 0.97: return None
    e = op[j]
    if kind == 'A': risk = 1.5 * atr; stop = e - risk; tgt = e + 1.5 * atr
    elif kind == 'B': risk = 2.0 * atr; stop = e - risk; tgt = None
    else:
        stop = sweep_low - 0.1 * atr
        risk = min(max(e - stop, 0.5 * atr), 2.5 * atr); stop = e - risk; tgt = e + 2 * risk
    x = walk(op, hi, lo, cl, j, n, e, stop, tgt)
    if x is None: return None
    return (x - e) / risk - COST * e / risk


KINDS = ['A', 'B', 'C']
FAMS = ['BASE', 'SWEEP', 'SWEEP_UP', 'SWEEP_EQL', 'SWEEP_EQL_UP', 'SWEEP_LOC', 'SWEEP_VOL', 'SWEEP_EQL_LOC_UP', 'SWEEP_DEEP']
res = {f: {k: [] for k in KINDS} for f in FAMS}      # (year, R)
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 130: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]
    cl = [byd[d][3] for d in ds]; vol = [byd[d][4] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]
    e50 = ema(cl, 50)
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    bp = 0; last_bad = -10 ** 9
    for i in range(60, n - HOLD - 2):
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]; bp += 1
        if last_bad > i - 90: continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5 or cl[i] > 6000: continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / cl[i] < 0.004: continue
        y = ds[i].year
        fam = []
        if i % 5 == 0: fam.append('BASE')
        L = min(lo[i - 20:i])
        if lo[i] < L and cl[i] > L:
            up = cl[i] > e50[i]
            rng = hi[i] - lo[i]
            loc = rng > 0 and (cl[i] - lo[i]) / rng >= 0.5
            eql = sum(1 for k in range(i - 20, i) if lo[k] <= L * 1.005) >= 2
            v20 = sum(vol[i - 20:i]) / 20.0
            fam.append('SWEEP')
            if up: fam.append('SWEEP_UP')
            if eql: fam.append('SWEEP_EQL')
            if eql and up: fam.append('SWEEP_EQL_UP')
            if loc: fam.append('SWEEP_LOC')
            if v20 and vol[i] >= 1.5 * v20: fam.append('SWEEP_VOL')
            if eql and loc and up: fam.append('SWEEP_EQL_LOC_UP')
            if (L - lo[i]) >= 0.5 * atr: fam.append('SWEEP_DEEP')
        if not fam: continue
        sl = lo[i]
        for k in KINDS:
            r_ = trade(op, hi, lo, cl, i, n, atr, k, sl)
            if r_ is None: continue
            for f in fam: res[f][k].append((y, r_))

years = sorted({d.year for d in alldates})
rows = []
L_ = ['LIQUIDITY SWEEP STUDY (generated %s)' % datetime.date.today().isoformat(),
      'Data %s to %s, %d symbols. Liquid only. Event: low < prior-20d low but close back above it. Entry next open, hold 5 days, cost 0.25%%.' % (
          alldates[0], alldates[-1], len(data), ),
      'Exit A = stop 1.5 ATR / target 1.5 ATR. B = stop 2 ATR, 5-day close. C = stop just below sweep low, target 2R. EQL = old low touched >=2 times.',
      'TRAIN = years <= %d, TEST = later. BASE = random liquid stock-day (every 5th day).' % TRAIN_END, '']
hdr = '%-17s %2s %6s %4s %7s %5s | %7s %7s | ' % ('family', 'ex', 'n', 'win', 'avgR', 'PF', 'trainR', 'testR') + ' '.join('%6d' % y for y in years)
L_.append(hdr)
for k in KINDS:
    for f in FAMS:
        v = res[f][k]
        if len(v) < 50: continue
        vals = [x for _, x in v]; m = len(vals)
        gp = sum(x for x in vals if x > 0); gl = -sum(x for x in vals if x < 0)
        tr_ = [x for y, x in v if y <= TRAIN_END]; te_ = [x for y, x in v if y > TRAIN_END]
        yr = []
        for yy in years:
            yv = [x for y, x in v if y == yy]
            yr.append(sum(yv) / len(yv) if len(yv) >= 30 else float('nan'))
        L_.append('%-17s %2s %6d %3d%% %7.3f %5.2f | %7.3f %7.3f | ' % (f, k, m, round(100.0 * sum(1 for x in vals if x > 0) / m), sum(vals) / m,
                  gp / gl if gl > 0 else 9.99, sum(tr_) / len(tr_) if tr_ else 0, sum(te_) / len(te_) if te_ else 0) + ' '.join('%6.3f' % z for z in yr))
        rows.append(dict(family=f, exit=k, n=m, avgR=round(sum(vals) / m, 3), train=round(sum(tr_) / len(tr_), 3) if tr_ else 0,
                         test=round(sum(te_) / len(te_), 3) if te_ else 0))
    L_.append('')
L_.append('Read: a sweep family is useful only if avgR beats BASE clearly AND train and test are both positive. Past results do not guarantee future results.')
with open(os.path.join(out_dir, 'sweep_results.csv'), 'w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
open(os.path.join(out_dir, 'sweep_summary.txt'), 'w', encoding='utf-8').write('\n'.join(L_) + '\n')
print('\n'.join(L_))
