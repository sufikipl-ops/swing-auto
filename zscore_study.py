# Reel "Z-score mean reversion": z = (close - 20 din ka average) / 20 din ka std. z <= -2 (bahut gira) -> kal open par kharido,
# wapas 20-din average ko chhuye to becho. Stop-loss + time-stop (reel: "teen din me wapas nahi aaya to bahar").
# Reel ka hook bhi: "jo stock aaj 10% gira, kal wahi kharido". (Rule reel ki captions se, jo bola gaya wahi likha tha.)
# Daily NSE bhavcopy ~4 saal, liquid stocks (20-din turnover 5 cr+). Kal OPEN par entry, gap filter (open +1.5% upar / -3% neeche
# = skip), kharcha 0.25%, same din SL aur target = SL. Market haal (breadth) ke hisaab se alag, saal-war bhi.
# usage: python zscore_study.py <bhav_folder> <out_folder>    (SYNTH=1 -> random walk sanity)
import os, sys, csv, glob, json, math, random, datetime, collections

COST = 0.0025
GAP_UP, GAP_DN = 1.015, 0.97
LINES = []


def log(s=''):
    print(s, flush=True); LINES.append(s)


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


def load(bhav):
    data = collections.defaultdict(dict)
    for f in glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')):
        with open(f, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[1].strip() != 'EQ':
                    continue
                try:
                    d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
                except ValueError:
                    continue
                t = [num(r[k]) for k in (4, 5, 6, 8, 11)]
                if None in t or t[3] <= 0:
                    continue
                data[r[0].strip()][d] = (t[0], t[1], t[2], t[3], t[4] / 100.0)
    return data


def synth():
    rnd = random.Random(11); d0 = datetime.date(2022, 1, 3); dates = []; d = d0
    while len(dates) < 1000:
        if d.weekday() < 5: dates.append(d)
        d += datetime.timedelta(1)
    out = {}
    for s in range(500):
        px = 100 * math.exp(rnd.gauss(0, 1)); vol = rnd.uniform(0.012, 0.035); byd = {}
        for dd in dates:
            o = px * math.exp(rnd.gauss(0, vol * 0.3)); hi = lo = o; px = o
            for _ in range(30):
                px *= math.exp(rnd.gauss(0, vol / math.sqrt(30))); hi = max(hi, px); lo = min(lo, px)
            byd[dd] = (o, hi, lo, px, 50.0)
        out['S%03d' % s] = byd
    return out


def main():
    syn = bool(os.environ.get('SYNTH'))
    out_dir = sys.argv[2] if len(sys.argv) > 2 else 'out'
    os.makedirs(out_dir, exist_ok=True)
    data = synth() if syn else load(sys.argv[1])
    alld = sorted({d for v in data.values() for d in v})
    # market haal (liquid stocks % EMA50 ke upar)
    ab, tot = collections.Counter(), collections.Counter(); a50 = 2.0 / 51
    for byd in data.values():
        ds = sorted(byd); e = None
        for k, d in enumerate(ds):
            c = byd[d][3]; e = c if e is None else a50 * c + (1 - a50) * e
            if k >= 60 and byd[d][4] >= 1:
                tot[d] += 1; ab[d] += c > e
    reg = {d: ('STRONG' if 100.0 * ab[d] / tot[d] >= 60 else 'MIXED' if 100.0 * ab[d] / tot[d] >= 40 else 'WEAK' if 100.0 * ab[d] / tot[d] >= 25 else 'VWEAK')
           for d in alld if tot[d] >= 50}
    log('Z-SCORE MEAN REVERSION STUDY%s (%s): data %s se %s, %d stocks' % (' [SYNTH]' if syn else '', datetime.date.today(), alld[0], alld[-1], len(data)))
    # variants: (naam, z cut, SL ATR guna ya None, max din, trend filter)
    VARS = [('REEL: Z-2 / SL2ATR / 3d', -2.0, 2.0, 3, None), ('REEL: Z-2 / bina SL / 3d', -2.0, None, 3, None),
            ('REEL: Z-2 / SL3ATR / 3d', -2.0, 3.0, 3, None), ('REEL: 10% gira / SL2ATR / 3d', 'D10', 2.0, 3, None),
            ('REEL: 10% gira / bina SL / 3d', 'D10', None, 3, None), ('Z-2 / SL2ATR / 10d', -2.0, 2.0, 10, None), ('Z-2 / SL3ATR / 20d', -2.0, 3.0, 20, None),
            ('Z-2 / bina SL / 10d', -2.0, None, 10, None), ('Z-2.5 / SL2ATR / 10d', -2.5, 2.0, 10, None),
            ('Z-2 / SL2ATR / 10d + EMA200 upar', -2.0, 2.0, 10, 'up'), ('Z-2 / SL2ATR / 10d + EMA200 neeche', -2.0, 2.0, 10, 'down'),
            ('BASE: koi bhi din / SL2ATR / 10d', None, 2.0, 10, None), ('BASE: koi bhi din / SL2ATR / 3d', None, 2.0, 3, None)]
    R = collections.defaultdict(list)
    rnd = random.Random(3)
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 230:
            continue
        b = [byd[d] for d in ds]
        o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]; to = [x[4] for x in b]
        e200 = None; a2 = 2.0 / 201; E = []
        for x in c:
            e200 = x if e200 is None else a2 * x + (1 - a2) * e200; E.append(e200)
        busy = {v[0]: -1 for v in VARS}
        for i in range(200, len(c) - 1):
            if any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 20, i + 1)):
                continue                         # split/bonus ke paas nahi
            w = c[i - 19:i + 1]; m = sum(w) / 20.0; sd = math.sqrt(sum((x - m) ** 2 for x in w) / 20.0)
            if sd <= 0 or sum(to[i - 19:i + 1]) / 20.0 < 5:
                continue
            z = (c[i] - m) / sd
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]
            atr = sum(tr) / 14.0
            for name, zc, slm, maxd, tf in VARS:
                if i <= busy[name]:
                    continue                     # ek stock me ek waqt ek hi trade
                if zc is None:
                    if rnd.random() > 0.02: continue
                elif zc == 'D10':
                    if c[i] > c[i - 1] * 0.90: continue          # aaj 10%+ gira
                elif z > zc:
                    continue
                if tf == 'up' and c[i] < E[i]: continue
                if tf == 'down' and c[i] >= E[i]: continue
                j = i + 1
                if o[j] > c[i] * GAP_UP or o[j] < c[i] * GAP_DN:
                    continue
                e = o[j]; stop = e - slm * atr if slm else None; risk = slm * atr if slm else 2 * atr
                ex = None
                for k in range(j, min(len(c), j + maxd)):
                    if stop and l[k] <= stop:
                        ex = (min(o[k], stop) if k > j else stop, k, 'SL'); break
                    mk = sum(c[k - 20:k]) / 20.0          # aaj ke din pata 20-din average (kal tak ke close)
                    if zc is not None and h[k] >= mk and mk > e:
                        ex = (max(o[k], mk) if k > j else mk, k, 'Average'); break
                if ex is None:
                    k = min(len(c), j + maxd) - 1; ex = (c[k], k, 'Time')
                busy[name] = ex[1]
                r_ = (ex[0] - e) / risk - COST * e / risk
                for rg in (reg.get(ds[i], '?'), 'ALL'):
                    R[(name, rg)].append((ds[i].year, r_, (ex[0] / e - 1) * 100 - COST * 100, ex[2], ex[1] - j + 1))
    log('R = kharcha kaat ke, risk = SL door (bina SL wale me 2 ATR). Jeet = R>0. "saal+" = kitne saal (20+ trade) avg plus.')
    log('%-36s %-7s %6s %5s %8s %7s %6s  %-14s %s' % ('variant', 'market', 'n', 'jeet', 'avgR', 'avg%', 'din', 'exit SL/Avg/T', 'saal+'))
    rows = []
    for name, *_ in VARS:
        for rg in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
            v = R.get((name, rg))
            if not v:
                continue
            n = len(v); avg = sum(x[1] for x in v) / n; pc = sum(x[2] for x in v) / n
            ex = collections.Counter(x[3] for x in v); yrs = collections.defaultdict(list)
            for y, r_, *_ in v: yrs[y].append(r_)
            yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
            row = dict(variant=name, regime=rg, n=n, win=round(100.0 * sum(1 for x in v if x[1] > 0) / n), avgR=round(avg, 3), avgpct=round(pc, 2),
                       days=round(sum(x[4] for x in v) / n, 1), sl=ex['SL'], avgx=ex['Average'], time=ex['Time'], years='%d/%d' % (yp, yt))
            rows.append(row)
            log('%-36s %-7s %6d %4d%% %+8.3f %+6.2f%% %6.1f  %4d/%4d/%4d  %s' % (name, rg, n, row['win'], avg, pc, row['days'], ex['SL'], ex['Average'], ex['Time'], row['years']))
        log('')
    base = {r['regime']: r['avgR'] for r in rows if r['variant'] == 'BASE: koi bhi din / SL2ATR / 10d'}
    base3 = {r['regime']: r['avgR'] for r in rows if r['variant'] == 'BASE: koi bhi din / SL2ATR / 3d'}
    good = [r for r in rows if not r['variant'].startswith('BASE') and r['n'] >= 100 and r['avgR'] > 0.05 and r['avgR'] - (base3 if '/ 3d' in r['variant'] else base).get(r['regime'], 0) >= 0.05
            and int(r['years'].split('/')[0]) * 2 > int(r['years'].split('/')[1])]
    log('PASS (n>=100, avgR>+0.05, BASE se 0.05R+ behtar, zyada saal plus): %s' % (
        '; '.join('%s %s %+.3f (n %d)' % (r['variant'], r['regime'], r['avgR'], r['n']) for r in good) or 'koi nahi'))
    suf = '_synth' if syn else ''
    open(os.path.join(out_dir, 'zscore_summary%s.txt' % suf), 'w').write('\n'.join(LINES) + '\n')
    with open(os.path.join(out_dir, 'zscore_results%s.csv' % suf), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


if __name__ == '__main__':
    main()
