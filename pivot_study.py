# Does the reel setup (Traditional Pivot + EMA9) add anything? Tested on ~4 years of NSE bhavcopy.
# usage: python pivot_study.py <bhav_folder> <out_folder>   -> pivot_summary.txt + pivot_results.csv
# Same honest rules as dip_study.py: next-day OPEN entry, cost 0.25% round trip, same-bar stop+target = stop,
# gap-up >1.5% / gap-down >3% skipped, 90 days after a >35% jump skipped, liquid only (turnover20 >= Rs5cr).
# Pivot levels use the standard daily formula; "pivot of bar j" = levels that apply to the NEXT session.
import csv, glob, os, sys, datetime, collections

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
COST = 0.25 / 100.0
GAP_UP, GAP_DN = 1.015, 0.97
EXITS = [(2.0, 5, None), (2.0, 5, 1.5), (3.0, 5, None), (2.0, 10, None)]
MIN_N = 200


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


def sim(op, hi, lo, cl, i, n, atr, stop_m, hold, tgt):
    j = i + 1
    if j >= n: return None
    if op[j] > cl[i] * GAP_UP or op[j] < cl[i] * GAP_DN: return None
    entry = op[j]; risk = stop_m * atr; stop = entry - risk
    target = entry + tgt * risk if tgt else None
    end = min(j + hold, n)
    if end - j < hold: return None
    exit_p = None
    for k in range(j, end):
        if k > j and op[k] <= stop: exit_p = op[k]; break
        if lo[k] <= stop: exit_p = stop; break
        if target is not None and hi[k] >= target: exit_p = target; break
    if exit_p is None: exit_p = cl[end - 1]
    return (exit_p - entry) / risk - COST * entry / risk


DIPS = [(-0.03, 'U1'), (-0.03, 'U2'), (-0.05, 'U1'), (-0.05, 'U2'), (-0.08, 'U1'), (-0.08, 'U2')]
FILTERS = ['NONE', 'E9', 'P', 'E9+P', 'S1HOLD']
# results[(family, name)] -> list per exit of list of (year, R)
res = collections.defaultdict(lambda: [[] for _ in EXITS])
base = [[] for _ in EXITS]

for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 130: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]
    cl = [byd[d][3] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]
    e9 = ema(cl, 9); e20 = ema(cl, 20); e50 = ema(cl, 50); rs = rsi14(cl)
    P = [(hi[i] + lo[i] + cl[i]) / 3.0 for i in range(n)]
    R1 = [2 * P[i] - lo[i] for i in range(n)]
    S1 = [2 * P[i] - hi[i] for i in range(n)]
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    bp = 0; last_bad = -10 ** 9
    for i in range(60, n):
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]; bp += 1
        if last_bad > i - 90 or i + 12 >= n: continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5 or cl[i] > 6000: continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / cl[i] < 0.004: continue
        y = ds[i].year
        pP, pR1, pS1 = P[i - 1], R1[i - 1], S1[i - 1]      # levels that were live on day i
        up1 = cl[i] > e50[i] and e20[i] > e50[i]
        sims = None

        def get():
            return [sim(op, hi, lo, cl, i, n, atr, s, h, t) for (s, h, t) in EXITS]

        def add(key):
            global sims
            r_ = get()
            for k, v in enumerate(r_):
                if v is not None: res[key][k].append((y, v))

        if i % 5 == 0:
            for k, v in enumerate(get()):
                if v is not None: base[k].append((y, v))
        # --- family 1: dip in uptrend + pivot/EMA9 filter
        ret3 = cl[i] / cl[i - 3] - 1
        if up1:
            rs60 = cl[i] / cl[i - 60] - 1
            up2 = e50[i] > e50[i - 10] and rs60 > 0 and (rs[i] is not None and rs[i] < 45)
            fl = {'NONE': True, 'E9': cl[i] > e9[i], 'P': cl[i] > pP, 'E9+P': cl[i] > e9[i] and cl[i] > pP,
                  'S1HOLD': lo[i] <= pS1 and cl[i] > pS1}
            for thr, tn in DIPS:
                if ret3 > thr: continue
                if tn == 'U2' and not up2: continue
                for fn in FILTERS:
                    if fl[fn]: add(('DIP %d%% %s' % (int(thr * 100), tn), fn))
        # --- family 2: the reel's own idea, standalone (uptrend + EMA9 rising)
        if up1 and cl[i] > e9[i] and e9[i] > e9[i - 3]:
            if cl[i - 1] <= P[i - 2] and cl[i] > pP:
                add(('REEL', 'CROSS_P'))
            if cl[i - 1] <= R1[i - 2] and cl[i] > pR1:
                add(('REEL', 'CROSS_R1'))
            if cl[i - 1] <= S1[i - 2] and cl[i] > pS1 and lo[i] <= pS1:
                add(('REEL', 'S1_BOUNCE'))


def agg(v):
    n = len(v)
    if not n: return 0, 0.0, 0.0, 0
    vals = [x for _, x in v]
    gp = sum(x for x in vals if x > 0); gl = -sum(x for x in vals if x < 0)
    return n, sum(vals) / n, (gp / gl if gl > 0 else 9.99), round(100.0 * sum(1 for x in vals if x > 0) / n)


years = sorted({d.year for d in alldates})
rows = []
for (fam, fn), per in res.items():
    for k, (s, h, t) in enumerate(EXITS):
        v = per[k]
        n, avg, pf, win = agg(v)
        yr = {}
        for yy in years:
            yv = [x for y_, x in v if y_ == yy]
            yr[yy] = (len(yv), (sum(yv) / len(yv)) if yv else 0.0)
        rows.append(dict(family=fam, filt=fn, stop=s, hold=h, tgt=t or 0, n=n, win=win, avgR=round(avg, 3), pf=round(pf, 2),
                         **{'R_%d' % yy: round(yr[yy][1], 3) for yy in years}, **{'n_%d' % yy: yr[yy][0] for yy in years}))
with open(os.path.join(out_dir, 'pivot_results.csv'), 'w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


def fmt(r):
    return '%-11s %-8s %4.1f %3d %4s %6d %4d %7.3f %5.2f ' % (r['family'], r['filt'], r['stop'], r['hold'], r['tgt'] or '-',
        r['n'], r['win'], r['avgR'], r['pf']) + ' '.join('%7.3f' % r['R_%d' % yy] for yy in years)


hdr = '%-11s %-8s %4s %3s %4s %6s %4s %7s %5s ' % ('family', 'filter', 'stop', 'hld', 'tgt', 'n', 'win', 'avgR', 'PF') + \
      ' '.join('%7d' % yy for yy in years)
L = ['PIVOT + EMA9 STUDY (generated %s)' % datetime.date.today().isoformat(),
     'Data %s to %s, %d days, %d symbols. Liquid only. Entry = next open, cost 0.25%%, R = profit / (stop ATR x 14d ATR).' % (
         alldates[0], alldates[-1], len(alldates), len(data)),
     'DIP rows: dip-in-uptrend signal (same as dip_study) with an extra filter on signal day: E9 = close > EMA9, P = close > pivot',
     'live that day, E9+P = both, S1HOLD = low touched S1 and close back above it. NONE = no extra filter (compare against this).',
     'REEL rows: the reel idea alone (uptrend, EMA9 rising, close crosses above P / R1, or bounces off S1).', '']
L.append('== BASE (random liquid stock every 5th day) ==')
for k, (s, h, t) in enumerate(EXITS):
    n, avg, pf, win = agg(base[k])
    L.append('stop %.1f hold %d tgt %s: n %d win %d%% avgR %.3f PF %.2f' % (s, h, t or '-', n, win, avg, pf))
L.append('')
good = [r for r in rows if r['n'] >= MIN_N]
L.append('== DIP: does each filter beat NONE? (same dip, same exit; n >= %d) ==' % MIN_N); L.append(hdr)
for fam in sorted({r['family'] for r in good if r['family'] != 'REEL'}):
    for s, h, t in EXITS[:1] + EXITS[3:4]:
        for fn in FILTERS:
            for r in good:
                if r['family'] == fam and r['filt'] == fn and r['stop'] == s and r['hold'] == h and (r['tgt'] or None) == t:
                    L.append(fmt(r))
        L.append('')
L.append('== REEL standalone (all exits) =='); L.append(hdr)
for r in sorted([r for r in rows if r['family'] == 'REEL'], key=lambda x: (x['filt'], x['stop'], x['hold'])): L.append(fmt(r))
L.append('')
L.append('== TOP 15 by avgR overall (n >= %d) ==' % MIN_N); L.append(hdr)
for r in sorted(good, key=lambda x: -x['avgR'])[:15]: L.append(fmt(r))
L.append('')
L.append('Many combos tried: a filter is only interesting if avgR beats NONE AND stays positive in most years with big n.')
L.append('Past results do not guarantee future results.')
open(os.path.join(out_dir, 'pivot_summary.txt'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
