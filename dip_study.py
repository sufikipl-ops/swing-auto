# Long-history study of the only near-breakeven idea so far: DIP IN UPTREND (liquid stocks).
# usage: python dip_study.py <bhav_folder> <out_folder>
# Writes dip_summary.txt + dip_results.csv. Honest rules: next-day OPEN entry, cost 0.25% round trip,
# same-bar stop+target = stop, gap-up >1.5% or gap-down >3% skipped, 90 days after a >35% jump skipped (split/bonus).
import csv, glob, os, sys, datetime, collections
from array import array

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
COST = 0.25 / 100.0
GAP_UP, GAP_DN = 1.015, 0.97
THRS = [-0.03, -0.05, -0.08]
TRENDS = ['U1', 'U2']
REGIMES = ['ANY', 'BR40', 'BR50']
STOPS = [2.0, 3.0]
HOLDS = [3, 5, 10]
TARGETS = [None, 1.5]          # None = no target, exit at close of hold day
MIN_N = 300
EXITS = [(s, h, t) for s in STOPS for h in HOLDS for t in TARGETS]


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


def rsi14(cl):
    out = [None] * len(cl); au = ad = None; n = 0
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]; up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None: au, ad = up, dn
        else:
            au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
        n += 1
        if n >= 14: out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


# ---- load: per symbol dict date -> tuple(op,hi,lo,cl,vol,to)
data = collections.defaultdict(dict)
files = sorted(glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv')))
for f in files:
    with open(f, newline='', encoding='utf-8', errors='ignore') as h:
        rd = csv.reader(h); next(rd, None)
        for r in rd:
            if len(r) < 15: continue
            if r[1].strip() != 'EQ': continue
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

above = collections.Counter(); total = collections.Counter()
sigs = []        # (date, year, thr_ok bits..., results)
base = [[] for _ in EXITS]; base_year = [collections.defaultdict(list) for _ in EXITS]


def sim(op, hi, lo, cl, i, n, atr, stop_m, hold, tgt):
    j = i + 1
    if j >= n: return None
    if op[j] > cl[i] * GAP_UP or op[j] < cl[i] * GAP_DN: return None
    entry = op[j]; risk = stop_m * atr; stop = entry - risk
    target = entry + tgt * risk if tgt else None
    end = min(j + hold, n)
    if end - j < hold: return None            # not enough future bars
    exit_p = None
    for k in range(j, end):
        if k > j and op[k] <= stop: exit_p = op[k]; break
        if lo[k] <= stop: exit_p = stop; break
        if target is not None and hi[k] >= target: exit_p = target; break
    if exit_p is None: exit_p = cl[end - 1]
    return (exit_p - entry) / risk - COST * entry / risk


for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 130: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]
    cl = [byd[d][3] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]
    e20 = ema(cl, 20); e50 = ema(cl, 50); rs = rsi14(cl)
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    bp = 0; last_bad = -10 ** 9
    for i in range(60, n):
        d = ds[i]
        total[d] += 1
        if cl[i] > e50[i]: above[d] += 1
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]; bp += 1
        if last_bad > i - 90 or i + 12 >= n: continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5 or cl[i] > 6000: continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / cl[i] < 0.004: continue
        res = [sim(op, hi, lo, cl, i, n, atr, s, h, t) for (s, h, t) in EXITS]
        if i % 5 == 0:                                   # BASE: random liquid stock every 5th day
            for k, r_ in enumerate(res):
                if r_ is not None: base[k].append(r_); base_year[k][d.year].append(r_)
        ret3 = cl[i] / cl[i - 3] - 1
        if ret3 > THRS[0]: continue
        up1 = cl[i] > e50[i] and e20[i] > e50[i]
        if not up1: continue
        rs60 = cl[i] / cl[i - 60] - 1
        up2 = e50[i] > e50[i - 10] and rs60 > 0 and (rs[i] is not None and rs[i] < 45)
        sigs.append((d, ret3, up2, res))
print('signals', len(sigs))


def agg(v):
    n = len(v)
    if not n: return 0, 0.0, 0.0, 0
    gp = sum(x for x in v if x > 0); gl = -sum(x for x in v if x < 0)
    return n, sum(v) / n, (gp / gl if gl > 0 else 9.99), round(100.0 * sum(1 for x in v if x > 0) / n)


years = sorted({d.year for d in alldates if d.year >= alldates[0].year})
rows = []
for thr in THRS:
    for tr_ in TRENDS:
        for rg in REGIMES:
            sel = []
            for (d, ret3, up2, res) in sigs:
                if ret3 > thr: continue
                if tr_ == 'U2' and not up2: continue
                b = above[d] / float(total[d]) if total[d] else 0
                if rg == 'BR40' and b < 0.40: continue
                if rg == 'BR50' and b < 0.50: continue
                sel.append((d, res))
            for k, (s, h, t) in enumerate(EXITS):
                vals = [(d, r[k]) for d, r in sel if r[k] is not None]
                n, avg, pf, win = agg([v for _, v in vals])
                yr = {}
                for y in years:
                    yv = [v for d, v in vals if d.year == y]
                    yr[y] = (len(yv), (sum(yv) / len(yv)) if yv else 0.0)
                rows.append(dict(thr=int(thr * 100), trend=tr_, regime=rg, stop=s, hold=h, tgt=t or 0, n=n, win=win,
                                 avgR=round(avg, 3), pf=round(pf, 2),
                                 **{'R_%d' % y: round(yr[y][1], 3) for y in years},
                                 **{'n_%d' % y: yr[y][0] for y in years}))
with open(os.path.join(out_dir, 'dip_results.csv'), 'w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


def minyear(r):
    return min(r['R_%d' % y] for y in years if r['n_%d' % y] >= 30) if any(r['n_%d' % y] >= 30 for y in years) else -9


def fmt(r):
    return '%4d %-3s %-4s %4.1f %3d %4s %6d %4d %7.3f %5.2f ' % (r['thr'], r['trend'], r['regime'], r['stop'], r['hold'],
        r['tgt'] or '-', r['n'], r['win'], r['avgR'], r['pf']) + ' '.join('%7.3f' % r['R_%d' % y] for y in years)


L = ['DIP STUDY (generated %s)' % datetime.date.today().isoformat(),
     'Data %s to %s, %d trading days, %d symbols. Liquid only (turnover20 >= Rs5cr, price <= 6000).' % (
         alldates[0], alldates[-1], len(alldates), len(data)),
     'Signal: 3-day drop <= thr% while close > EMA50 and EMA20 > EMA50 (U1); U2 adds EMA50 rising, 60d return > 0, RSI < 45.',
     'BR40/BR50 = share of all stocks above own EMA50 on signal day >= 40/50%. Entry = next open. Cost 0.25%.',
     'Years columns = avgR in that calendar year. R = profit / risk (risk = stop ATR x 14d ATR).', '']
hdr = '%4s %-3s %-4s %4s %3s %4s %6s %4s %7s %5s ' % ('thr', 'trd', 'reg', 'stop', 'hld', 'tgt', 'n', 'win', 'avgR', 'PF') + \
      ' '.join('%7d' % y for y in years)
L.append('== BASE (random liquid stock every 5th day), per exit ==')
L.append('stop hold tgt      n  avgR  | ' + ' '.join(str(y) for y in years))
for k, (s, h, t) in enumerate(EXITS):
    n, avg, pf, win = agg(base[k])
    L.append('%4.1f %4d %3s %6d %6.3f  | ' % (s, h, t or '-', n, avg) + ' '.join('%6.3f' % (
        sum(base_year[k][y]) / len(base_year[k][y]) if base_year[k][y] else 0) for y in years))
L.append('')
good = [r for r in rows if r['n'] >= MIN_N]
L.append('== TOP 25 by avgR (n >= %d) ==' % MIN_N); L.append(hdr)
for r in sorted(good, key=lambda x: -x['avgR'])[:25]: L.append(fmt(r))
L.append('')
allpos = [r for r in good if r['avgR'] > 0 and minyear(r) > 0]
L.append('Combos with avgR > 0 in EVERY year (years with n>=30): %d of %d' % (len(allpos), len(good)))
L.append(hdr)
for r in sorted(allpos, key=lambda x: -x['avgR'])[:20]: L.append(fmt(r))
L.append('')
L.append('Combos with avgR > 0 overall: %d of %d. Many combos were tried; trust only those positive in every year with big n.' % (
    sum(1 for r in good if r['avgR'] > 0), len(good)))
L.append('Past results do not guarantee future results.')
open(os.path.join(out_dir, 'dip_summary.txt'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
