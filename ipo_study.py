# Naye listing (IPO ke baad pehle 60 din) wale stocks: kya "listing ke baad ke low ke paas aaya -> bounce" chalta hai?
# User ka idea: naya stock apne low par ho aur niche jaane ki jagah na ho to trade; fundamentals strong ho aur bina wajah gire
# to bounce. (Purane fundamentals/news ka itihas hamare paas nahi, isliye yahan sirf price wala hissa test hota hai.)
# Naya listing = symbol jo data shuru hone ke 60+ din baad pehli baar EQ me aaya. Din 3..59 (listing ke baad) dekhe jaate hain.
# Setups (aaj ke close par, kal open par entry, 0.25% kharcha, gap filter, same din SL+target = SL):
#   NEAR_LOW   : close listing-ke-baad-low se 0-3% upar (support ke paas, toota nahi)
#   REV_LOW    : aaj low us support ke 2% andar gaya, phir hari candle aur range ke upar aadhe me band (support se palta)
#   NEW_LOW    : close listing-ke-baad-low ke neeche (support toota)
#   BELOW_LIST : close listing din ke open se 15%+ neeche
#   DROP8      : 3 din me 8%+ gira (bina trend shart)
#   BASE       : koi bhi naya-listing din (tulna ke liye)
# Exit: (a) LOWSL = SL support ke 2% neeche (risk 1-12%), target 2R, max 10 din; (b) 2ATR/5d (regime_study jaisa).
# Market haal: liquid stocks me % EMA50 ke upar (regime_study jaisa).
# usage: python ipo_study.py <bhav_folder> <out_folder>   (SYNTH=1 -> random walk sanity)
import csv, glob, os, sys, json, math, random, datetime, collections

COST = 0.25 / 100.0
GAP_UP, GAP_DN = 1.015, 0.97
MIN_LATE = 60          # data shuru hone ke itne din baad pehli baar dikhe tabhi "naya listing"
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
    for f in sorted(glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv'))):
        with open(f, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[1].strip() not in ('EQ', 'BE'): continue
                try:
                    d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
                except ValueError:
                    continue
                t = tuple(num(r[k]) for k in (4, 5, 6, 8, 11))
                if None in t or t[3] <= 0: continue
                data[r[0].strip()][d] = (t[0], t[1], t[2], t[3], t[4] / 100.0)     # o h l c, turnover cr
    return data


def synth():
    rnd = random.Random(7); d0 = datetime.date(2022, 1, 3); dates = []
    d = d0
    while len(dates) < 1000:
        if d.weekday() < 5: dates.append(d)
        d += datetime.timedelta(1)
    data = {}
    for s in range(1500):
        st = 0 if s < 600 else rnd.randint(70, 950); px = 100 * math.exp(rnd.gauss(0, 1)); vol = rnd.uniform(0.015, 0.04); byd = {}
        for d in dates[st:]:
            o = px; hi = lo = px
            for _ in range(40):
                px *= math.exp(rnd.gauss(0, vol / math.sqrt(40))); hi = max(hi, px); lo = min(lo, px)
            byd[d] = (o, hi, lo, px, 20.0)
        data['S%04d' % s] = byd
    return data


def regime_map(data, alld):
    ab, tot = collections.Counter(), collections.Counter(); a = 2.0 / 51
    for byd in data.values():
        ds = sorted(byd); e = None
        for k, d in enumerate(ds):
            c = byd[d][3]; e = c if e is None else a * c + (1 - a) * e
            if k >= 60 and byd[d][4] >= 1:
                tot[d] += 1; ab[d] += c > e
    out = {}
    for d in alld:
        if tot[d] >= 50:
            p = 100.0 * ab[d] / tot[d]
            out[d] = 'STRONG' if p >= 60 else 'MIXED' if p >= 40 else 'WEAK' if p >= 25 else 'VWEAK'
    return out


def run_trade(o, h, l, c, i, stop, tgt, hold):
    """Kal (i+1) open par entry. -> R (kharcha kaat ke) ya None."""
    j = i + 1
    if j >= len(c) or o[j] > c[i] * GAP_UP or o[j] < c[i] * GAP_DN: return None
    e = o[j]; risk = e - stop
    if risk <= 0: return None
    tg = e + tgt * risk if tgt else None
    for k in range(j, min(len(c), j + hold)):
        if l[k] <= stop:
            ex = min(o[k], stop) if k > j else stop
            return (ex - e) / risk - COST * e / risk
        if tg and h[k] >= tg:
            return tgt - COST * e / risk
    k = min(len(c), j + hold) - 1
    return (c[k] - e) / risk - COST * e / risk


def main():
    os.makedirs(sys.argv[2] if len(sys.argv) > 2 else 'out', exist_ok=True)
    out_dir = sys.argv[2] if len(sys.argv) > 2 else 'out'
    syn = bool(os.environ.get('SYNTH'))
    data = synth() if syn else load(sys.argv[1])
    alld = sorted({d for v in data.values() for d in v})
    reg = regime_map(data, alld)
    first_ok = alld[MIN_LATE] if len(alld) > MIN_LATE else alld[-1]
    log('NAYE LISTING STUDY%s (%s): data %s se %s, %d stocks' % (' [SYNTH]' if syn else '', datetime.date.today(), alld[0], alld[-1], len(data)))
    R = collections.defaultdict(list); n_ipo = 0
    for sym, byd in data.items():
        ds = sorted(byd)
        if ds[0] < first_ok or len(ds) < 8: continue
        # bich me lamba gap = shayad naam badla/relisting: skip
        if any((ds[k] - ds[k - 1]).days > 20 for k in range(1, min(len(ds), 60))): continue
        b = [byd[d] for d in ds]
        o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]; to = [x[4] for x in b]
        n_ipo += 1
        for i in range(3, min(60, len(c) - 1)):
            if sorted(to[max(0, i - 4):i + 1])[len(to[max(0, i - 4):i + 1]) // 2] < 2: continue      # 2 cr+ roz ka turnover
            lowp = min(l[:i])                          # aaj se pehle ka listing-ke-baad low
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(max(1, i - 13), i + 1)]
            atr = sum(tr) / len(tr)
            sig = ['BASE']
            if lowp < c[i] <= lowp * 1.03: sig.append('NEAR_LOW')
            if l[i] <= lowp * 1.02 and c[i] > o[i] and c[i] >= (h[i] + l[i]) / 2 and c[i] > lowp: sig.append('REV_LOW')
            if c[i] < lowp: sig.append('NEW_LOW')
            if c[i] < o[0] * 0.85: sig.append('BELOW_LIST')
            if c[i] <= c[i - 3] * 0.92: sig.append('DROP8')
            rg = reg.get(ds[i], '?'); yr = ds[i].year
            sup = min(lowp, l[i]) * 0.98
            for s in sig:
                e_ref = c[i]
                r1 = run_trade(o, h, l, c, i, sup, 2.0, 10) if 0.01 <= (e_ref - sup) / e_ref <= 0.12 else None
                r2 = run_trade(o, h, l, c, i, c[i] - 2 * atr, None, 5)
                for ex, r in (('LOWSL/10d/T2R', r1), ('2ATR/5d', r2)):
                    if r is None: continue
                    for rk in (rg, 'ALL'):
                        R[(s, ex, rk)].append((yr, r, sym))
    log('Naye listing mile: %d. R = kharcha (0.25%%) kaat ke. "saal+" = kitne saal (15+ trade wale) me avg plus.' % n_ipo)
    log('%-11s %-14s %-7s %6s %5s %8s %8s %8s  %s' % ('setup', 'exit', 'market', 'n', 'jeet', 'avgR', 'BASE', 'farak', 'saal+'))
    rows = []
    for k in sorted(R, key=lambda k: (k[1], k[0], k[2])):
        v = R[k]; n = len(v); rs = [x[1] for x in v]; avg = sum(rs) / n
        bv = R.get(('BASE', k[1], k[2]), []); base = sum(x[1] for x in bv) / len(bv) if bv else 0
        yrs = collections.defaultdict(list)
        for y, r, _ in v: yrs[y].append(r)
        yp = sum(1 for y in yrs if len(yrs[y]) >= 15 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 15)
        row = dict(setup=k[0], exit=k[1], regime=k[2], n=n, win=round(100.0 * sum(1 for r in rs if r > 0) / n), avgR=round(avg, 3),
                   baseR=round(base, 3), edge=round(avg - base, 3), years='%d/%d' % (yp, yt), stocks=len(set(x[2] for x in v)))
        rows.append(row)
        log('%-11s %-14s %-7s %6d %4d%% %+8.3f %+8.3f %+8.3f  %s' % (k[0], k[1], k[2], n, row['win'], avg, base, avg - base, row['years']))
    good = [r for r in rows if r['setup'] != 'BASE' and r['n'] >= 100 and r['avgR'] > 0.05 and r['edge'] >= 0.1
            and int(r['years'].split('/')[0]) >= 2 and int(r['years'].split('/')[0]) * 2 > int(r['years'].split('/')[1])]
    log('')
    log('PASS (n>=100, avgR>+0.05, BASE se 0.1R+ behtar, zyada saal plus): %s' % (', '.join('%s %s %s %+.3f (n %d)' % (r['setup'], r['exit'], r['regime'], r['avgR'], r['n']) for r in good) or 'koi nahi'))
    suf = '_synth' if syn else ''
    open(os.path.join(out_dir, 'ipo_summary%s.txt' % suf), 'w').write('\n'.join(LINES) + '\n')
    with open(os.path.join(out_dir, 'ipo_results%s.csv' % suf), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


if __name__ == '__main__':
    main()
