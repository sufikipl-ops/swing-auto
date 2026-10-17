# Owner ka idea: "zyada move karne wale (momentum) stock ko unke DIP ZONE par kharido".
# Test: momentum filter x dip zone x (optional) reversal candle, daily bhavcopy (~4 saal), liquid stocks.
# Honest rules (same as dip_study): next-day OPEN entry, cost 0.25% round trip, same-bar stop+target = stop,
# skip gap-up >1.5% / gap-down >3%, 90 days after a >35% jump skipped (split/bonus). TRAIN = <=2024, TEST = 2025+.
# usage: python momdip_study.py <bhav_folder> <out_folder>  -> momdip_summary.txt, momdip_results.csv
import csv, glob, os, sys, datetime, collections

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
COST = 0.25 / 100.0
GAP_UP, GAP_DN = 1.015, 0.97
EXITS = [(2.0, 5, None), (2.0, 5, 2.0), (2.0, 10, None), (2.0, 10, 2.0), (1.5, 10, 2.0)]   # (stop ATR, hold days, target R)
MIN_TRAIN, MIN_TEST = 150, 60


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
        else: au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
        n += 1
        if n >= 14: out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


# ---- load
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
print('files', len(files), 'symbols', len(data), 'dates', alldates[0], alldates[-1], len(alldates), flush=True)


def sim(op, hi, lo, cl, i, n, atr, stop_m, hold, tgt):
    j = i + 1
    if j >= n or op[j] > cl[i] * GAP_UP or op[j] < cl[i] * GAP_DN: return None
    entry = op[j]; risk = stop_m * atr; stop = entry - risk
    target = entry + tgt * risk if tgt else None
    end = min(j + hold, n)
    if end - j < hold: return None
    ex = None
    for k in range(j, end):
        if k > j and op[k] <= stop: ex = op[k]; break
        if lo[k] <= stop: ex = stop; break
        if target is not None and hi[k] >= target: ex = target; break
    if ex is None: ex = cl[end - 1]
    return (ex - entry) / risk - COST * entry / risk


# ---- pass 1: per symbol series + cross-sectional momentum / volatility ranks
S = {}
r60_by_date = collections.defaultdict(list); atrp_by_date = collections.defaultdict(list)
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 130: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]
    cl = [byd[d][3] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    atr = [None] * n
    for i in range(14, n): atr[i] = sum(tr[i - 13:i + 1]) / 14.0
    liq = [False] * n
    for i in range(60, n):
        to20 = sum(to[i - 20:i]) / 20.0
        liq[i] = to20 >= 5 and cl[i] <= 6000 and atr[i] and atr[i] / cl[i] >= 0.004
        if liq[i]:
            r60_by_date[ds[i]].append(cl[i] / cl[i - 60] - 1); atrp_by_date[ds[i]].append(atr[i] / cl[i])
    S[sym] = (ds, op, hi, lo, cl, atr, liq)


def pct(vals, q):
    v = sorted(vals); return v[min(len(v) - 1, int(q * len(v)))] if v else 9e9
R60_TOP = {d: pct(v, 0.80) for d, v in r60_by_date.items()}       # top 20% 60-din return
ATR_TOP = {d: pct(v, 0.70) for d, v in atrp_by_date.items()}      # top 30% roz ka move (ATR%)
print('ranked dates', len(R60_TOP), flush=True)

# ---- pass 2: signals
MOMS = ['UPTREND', 'MOM60', 'BIGMOVE', 'MOM60+BIGMOVE']
ZONES = ['DIP3_5', 'DIP3_8', 'EMA20_TOUCH', 'EMA50_TOUCH', 'OFF_HIGH_10', 'BREAKOUT_RETEST']
CONFS = ['ANY', 'REVERSAL_CANDLE']
res = collections.defaultdict(list)          # key -> list of (date, R)
base = collections.defaultdict(list)
for sym, (ds, op, hi, lo, cl, atr, liq) in S.items():
    n = len(ds)
    e20 = ema(cl, 20); e50 = ema(cl, 50)
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]; bp = 0; last_bad = -10 ** 9
    for i in range(70, n - 12):
        while bp < len(bad) and bad[bp] <= i: last_bad = bad[bp]; bp += 1
        if last_bad > i - 90 or not liq[i]: continue
        d = ds[i]
        R = None
        if i % 5 == 0:
            R = [sim(op, hi, lo, cl, i, n, atr[i], *x) for x in EXITS]
            for k, r_ in enumerate(R):
                if r_ is not None: base[k].append((d, r_))
        up = cl[i] > e50[i] and e20[i] > e50[i] and e50[i] > e50[i - 10]
        if not up: continue
        m60 = (cl[i] / cl[i - 60] - 1) >= R60_TOP.get(d, 9e9)
        big = atr[i] / cl[i] >= ATR_TOP.get(d, 9e9)
        moms = ['UPTREND'] + (['MOM60'] if m60 else []) + (['BIGMOVE'] if big else []) + (['MOM60+BIGMOVE'] if m60 and big else [])
        ret3 = cl[i] / cl[i - 3] - 1
        h20 = max(hi[i - 19:i + 1])
        res_lvl = max(hi[i - 60:i - 20]); broke = max(cl[i - 20:i]) > res_lvl * 1.02
        zones = []
        if ret3 <= -0.05: zones.append('DIP3_5')
        if ret3 <= -0.08: zones.append('DIP3_8')
        if lo[i] <= e20[i] * 1.005 and cl[i] >= e20[i] * 0.97: zones.append('EMA20_TOUCH')
        if lo[i] <= e50[i] * 1.01 and cl[i] >= e50[i] * 0.98: zones.append('EMA50_TOUCH')
        if cl[i] <= h20 * 0.90: zones.append('OFF_HIGH_10')
        if broke and lo[i] <= res_lvl * 1.02 and cl[i] >= res_lvl * 0.97: zones.append('BREAKOUT_RETEST')
        if not zones: continue
        rng = hi[i] - lo[i]
        rev = cl[i] > op[i] and rng > 0 and (cl[i] - lo[i]) / rng >= 0.6        # hara, upar ke 40% me band (hammer jaisa)
        confs = ['ANY'] + (['REVERSAL_CANDLE'] if rev else [])
        if R is None: R = [sim(op, hi, lo, cl, i, n, atr[i], *x) for x in EXITS]
        for m in moms:
            for z in zones:
                for c in confs:
                    for k, r_ in enumerate(R):
                        if r_ is not None: res[(m, z, c, k)].append((d, r_))
print('done signals', flush=True)


def agg(v):
    n = len(v)
    if not n: return dict(n=0, avg=0.0, pf=0.0, win=0)
    x = [r for _, r in v]; gp = sum(r for r in x if r > 0); gl = -sum(r for r in x if r < 0)
    return dict(n=n, avg=sum(x) / n, pf=gp / gl if gl else 9.99, win=round(100.0 * sum(1 for r in x if r > 0) / n))


years = sorted({d.year for d in alldates})
rows = []
for key, v in res.items():
    m, z, c, k = key
    tr_ = [p for p in v if p[0].year <= 2024]; te = [p for p in v if p[0].year > 2024]
    a, at, ae = agg(v), agg(tr_), agg(te)
    yr = {y: agg([p for p in v if p[0].year == y]) for y in years}
    rows.append(dict(momentum=m, zone=z, confirm=c, exit='%gATR/%dd/%s' % (EXITS[k][0], EXITS[k][1], ('T%gR' % EXITS[k][2]) if EXITS[k][2] else 'noT'),
                     n=a['n'], win=a['win'], avgR=round(a['avg'], 3), pf=round(a['pf'], 2), n_train=at['n'], trainR=round(at['avg'], 3),
                     n_test=ae['n'], testR=round(ae['avg'], 3), test_win=ae['win'],
                     **{'y%d' % y: (round(yr[y]['avg'], 3) if yr[y]['n'] >= 30 else '') for y in years}))
with open(os.path.join(out_dir, 'momdip_results.csv'), 'w', newline='') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

L = ['MOMENTUM + DIP ZONE STUDY (generated %s)' % datetime.date.today(),
     'Data %s to %s, liquid stocks (20-din turnover >= 5 cr). Entry next open, cost 0.25%%, gap filter. TRAIN = 2024 tak, TEST = 2025+.' % (alldates[0], alldates[-1]),
     'Momentum: UPTREND = close>EMA50, EMA20>EMA50, EMA50 upar | MOM60 = 60-din return top 20%% | BIGMOVE = ATR%% top 30%%.',
     'Zone: DIP3_5/8 = 3 din me -5/-8%% | EMA20/EMA50_TOUCH | OFF_HIGH_10 = 20-din high se 10%% neeche | BREAKOUT_RETEST = toota hua 60-din high wapas chhua.',
     'Confirm: REVERSAL_CANDLE = hari candle, din ke upar 40%% me band. Filters TRAIN par chuno, TEST par judge karo.', '']
for k, ex in enumerate(EXITS):
    b = agg(base[k]); bt = agg([p for p in base[k] if p[0].year > 2024])
    L.append('BASE (random liquid stock-day) %s: n %d avgR %.3f | test avgR %.3f' % (rows and '%gATR/%dd/%s' % (ex[0], ex[1], ('T%gR' % ex[2]) if ex[2] else 'noT'), b['n'], b['avg'], bt['avg']))
L.append('')
ok = [r for r in rows if r['n_train'] >= MIN_TRAIN and r['n_test'] >= MIN_TEST]
L.append('== TOP 25 by TRAIN avgR (n_train>=%d, n_test>=%d) -> dekho TEST bhi plus hai ya nahi ==' % (MIN_TRAIN, MIN_TEST))
hdr = '%-14s %-15s %-15s %-14s %6s %4s %7s %5s | %6s %7s | %6s %7s %4s | %s' % ('momentum', 'zone', 'confirm', 'exit', 'n', 'win', 'avgR', 'PF', 'nTr', 'trainR', 'nTe', 'testR', 'tW', ' '.join('y%d' % y for y in years))
L.append(hdr)
for r in sorted(ok, key=lambda r: -r['trainR'])[:25]:
    L.append('%-14s %-15s %-15s %-14s %6d %3d%% %7.3f %5.2f | %6d %7.3f | %6d %7.3f %3d%% | %s' % (
        r['momentum'], r['zone'], r['confirm'], r['exit'], r['n'], r['win'], r['avgR'], r['pf'], r['n_train'], r['trainR'], r['n_test'], r['testR'], r['test_win'],
        ' '.join(str(r['y%d' % y]) for y in years)))
both = [r for r in ok if r['trainR'] > 0 and r['testR'] > 0]
L.append('')
L.append('TRAIN aur TEST dono me plus: %d of %d combos. Sabse achhe (TEST avgR se):' % (len(both), len(ok)))
for r in sorted(both, key=lambda r: -r['testR'])[:15]:
    L.append('  %s | %s | %s | %s: train %.3f (n %d), test %.3f (n %d, win %d%%)' % (r['momentum'], r['zone'], r['confirm'], r['exit'], r['trainR'], r['n_train'], r['testR'], r['n_test'], r['test_win']))
ref = [r for r in ok if r['momentum'] == 'UPTREND' and r['zone'] == 'DIP3_8' and r['confirm'] == 'ANY']
L.append('')
L.append('Maujooda Dip (UPTREND + DIP3_8) comparison ke liye:')
for r in ref:
    L.append('  %s: train %.3f, test %.3f (n %d)' % (r['exit'], r['trainR'], r['testR'], r['n_test']))
L.append('Bahut combos dekhe: chhota plus luck ho sakta hai. Past results do not guarantee future results.')
open(os.path.join(out_dir, 'momdip_summary.txt'), 'w').write('\n'.join(L) + '\n')
print('\n'.join(L))
