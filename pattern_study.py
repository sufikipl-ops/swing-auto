# Which "eve of breakout" conditions actually lead to a profitable breakout?  usage: python pattern_study.py <bhav_folder> <out_folder>
# Writes pattern_summary.txt + pattern_buckets.csv + pattern_combos.csv
# Universe: every liquid stock-day j where the stock is below its 20-day high R20 (within 5%) and close > EMA50.
# Trade (what the app would do): buy-stop at R20*1.001 on day j+1 (skip if it opens > 1.5% above trigger / not triggered), hold 5 days.
#   Exit A: stop 1.5 ATR, target 2 ATR.   Exit B: stop 2 ATR, no target (day-5 close).   Cost 0.25%.
# Then: (1) winners vs losers feature medians, (2) each feature bucket vs overall (with per-year stability),
# (3) best 2-feature combos found on TRAIN years (<= 2024) and re-checked on TEST years (2025+), so we see what survives.
import csv, glob, os, sys, datetime, collections, itertools

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


def rsi_arr(cl):
    out = [None] * len(cl); au = ad = None; n = 0
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]; up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None: au, ad = up, dn
        else:
            au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
        n += 1
        if n >= 14: out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


def adx_arr(hi, lo, cl, n=14):
    N = len(cl); out = [None] * N
    if N < 2 * n + 2: return out
    tr = [0.0] * N; pdm = [0.0] * N; mdm = [0.0] * N
    for i in range(1, N):
        up = hi[i] - hi[i - 1]; dn = lo[i - 1] - lo[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    atr = sum(tr[1:n + 1]); p = sum(pdm[1:n + 1]); m = sum(mdm[1:n + 1]); dx = []
    for i in range(n + 1, N):
        atr = atr - atr / n + tr[i]; p = p - p / n + pdm[i]; m = m - m / n + mdm[i]
        pdi = 100 * p / atr if atr else 0; mdi = 100 * m / atr if atr else 0
        dx.append((i, 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0))
    if len(dx) < n: return out
    a = sum(x for _, x in dx[:n]) / n; out[dx[n - 1][0]] = a
    for i, x in dx[n:]:
        a = (a * (n - 1) + x) / n; out[i] = a
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


def sim(op, hi, lo, cl, j, n, trig, atr, s, t):
    if j >= n or hi[j] < trig or op[j] > trig * 1.015: return None
    entry = max(op[j], trig); risk = s * atr; stop = entry - risk
    target = entry + t * atr if t else None
    end = min(j + HOLD, n)
    if end - j < HOLD: return None
    exit_p = None
    for k in range(j, end):
        if k > j and op[k] <= stop: exit_p = op[k]; break
        if lo[k] <= stop: exit_p = stop; break
        if target is not None and hi[k] >= target: exit_p = target; break
    if exit_p is None: exit_p = cl[end - 1]
    return (exit_p - entry) / risk - COST * entry / risk


above = collections.Counter(); total = collections.Counter()
T = []          # one record per TRIGGERED trade: dict of numeric features + results
eves = 0; eve_year = collections.Counter()
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 130: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]
    cl = [byd[d][3] for d in ds]; vol = [byd[d][4] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]
    e20 = ema(cl, 20); e50 = ema(cl, 50); e200 = ema(cl, 200)
    rs = rsi_arr(cl); ax = adx_arr(hi, lo, cl)
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    bp = 0; last_bad = -10 ** 9
    for i in range(60, n):
        d = ds[i]
        total[d] += 1
        if cl[i] > e50[i]: above[d] += 1
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]; bp += 1
        if i + HOLD + 2 >= n or last_bad > i - 90: continue
        c = cl[i]
        if c <= e50[i] or c > 6000: continue
        R20 = max(hi[i - 19:i + 1])
        if c >= R20 or (R20 - c) / c > 0.05: continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5: continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / c < 0.004: continue
        eves += 1; eve_year[d.year] += 1
        trig = R20 * 1.001
        ra = sim(op, hi, lo, cl, i + 1, n, trig, atr, 1.5, 2.0)
        if ra is None: continue
        rb = sim(op, hi, lo, cl, i + 1, n, trig, atr, 2.0, None)
        v20 = sum(vol[i - 20:i]) / 20.0
        rng5 = sum(hi[k] - lo[k] for k in range(i - 4, i + 1)) / 5.0
        v5 = sum(vol[i - 4:i + 1]) / 5.0
        w = hi[i] - lo[i]
        h252 = max(hi[max(0, i - 251):i + 1])
        T.append(dict(date=d, year=d.year, ra=ra, rb=rb,
                      dist=(R20 - c) / atr, distp=(R20 - c) / c * 100, rng=rng5 / atr, vdry=(v5 / v20) if v20 else 1.0,
                      vtoday=(vol[i] / v20) if v20 else 1.0, rsi=rs[i], adx=ax[i], ret60=(c / cl[i - 60] - 1) * 100,
                      base=(R20 - min(lo[i - 19:i + 1])) / c * 100, touch=sum(1 for k in range(i - 19, i + 1) if hi[k] >= R20 * 0.99),
                      pos52=c / h252, loc=((c - lo[i]) / w) if w > 0 else 0.5, chg=(c / cl[i - 1] - 1) * 100,
                      e2050=1 if e20[i] > e50[i] else 0, a200=(1 if c > e200[i] else 0) if i >= 150 else -1,
                      slope=(e50[i] / e50[i - 10] - 1) * 100, atrp=atr / c * 100))
print('eve days', eves, 'triggered trades', len(T))
if not T:
    print('no trades'); sys.exit(1)
for t in T:
    t['br'] = 100.0 * above[t['date']] / total[t['date']] if total[t['date']] else 50.0
years = sorted({t['year'] for t in T})

FEATS = [  # name, label, edges (bucket i = value < edges[i], last = >= last edge)
    ('dist', 'Level se doori (ATR)', [0.25, 0.5, 1.0, 1.5]),
    ('rng', 'Range squeeze (5-din range / ATR)', [0.6, 0.8, 1.0, 1.3]),
    ('vdry', 'Volume shaant? (5-din vol / 20-din avg)', [0.7, 0.9, 1.1, 1.5]),
    ('rsi', 'RSI', [45, 50, 55, 60, 65, 70]),
    ('adx', 'ADX (trend dum)', [15, 20, 25, 30]),
    ('ret60', '60-din return %', [0, 10, 25, 50]),
    ('base', 'Base width % (20-din high-low)', [8, 12, 18, 30]),
    ('touch', 'Level ko kitni baar chhua (20 din)', [2, 3, 5]),
    ('pos52', 'Close / 52-hafte high', [0.7, 0.85, 0.95]),
    ('loc', 'Aaj ka close day-range me (0=low,1=high)', [0.3, 0.7]),
    ('chg', 'Aaj ka change %', [-1, 0, 1]),
    ('slope', 'EMA50 slope (10 din %)', [0, 2, 5]),
    ('br', 'Market breadth (% stocks > EMA50)', [30, 40, 50, 60]),
    ('e2050', 'EMA20 > EMA50', [1]),
    ('a200', 'Close > EMA200', [0, 1]),
    ('vtoday', 'Aaj ka volume / 20-din avg', [0.7, 1.0, 1.5]),
]


def bucket(v, edges):
    if v is None: return -1
    for k, e in enumerate(edges):
        if v < e: return k
    return len(edges)


def blabel(edges, k):
    if k < 0: return 'na'
    if k == 0: return '< %g' % edges[0]
    if k == len(edges): return '>= %g' % edges[-1]
    return '%g-%g' % (edges[k - 1], edges[k])


for t in T:
    t['b'] = [bucket(t[f], e) for f, _, e in FEATS]


def stats(rows, key='ra'):
    n = len(rows)
    if not n: return 0, 0, 0.0, 0.0
    vals = [r[key] for r in rows]
    gp = sum(x for x in vals if x > 0); gl = -sum(x for x in vals if x < 0)
    return n, round(100.0 * sum(1 for x in vals if x > 0) / n), sum(vals) / n, (gp / gl if gl > 0 else 9.99)


L = ['BREAKOUT PATTERN STUDY (generated %s)' % datetime.date.today().isoformat(),
     'Data %s to %s, %d symbols. Eve-of-breakout days (below 20d high within 5%%, close > EMA50, liquid): %d; triggered trades: %d.' % (
         alldates[0], alldates[-1], len(data), eves, len(T)),
     'Trade = buy-stop at 20d high x1.001 next day. Exit A = stop 1.5 ATR / target 2 ATR / 5 days. Exit B = stop 2 ATR, hold 5 days. Cost 0.25%.',
     'R = profit / risk. win = % trades profitable. PF = profit factor (>1 profit). Years = avgR of exit A in that year.', '']
n, w, a, pf = stats(T); n2, w2, a2, pf2 = stats(T, 'rb')
L.append('ALL triggered trades: n %d | exit A: win %d%% avgR %.3f PF %.2f | exit B: win %d%% avgR %.3f PF %.2f' % (n, w, a, pf, w2, a2, pf2))
L.append('Trigger rate: %.0f%% of eve days actually broke above the level next day.' % (100.0 * len(T) / max(eves, 1)))
L.append('')
# winners vs losers
win = [t for t in T if t['ra'] > 0]; los = [t for t in T if t['ra'] <= 0]


def med(rows, f):
    v = sorted(x[f] for x in rows if x[f] is not None)
    return v[len(v) // 2] if v else float('nan')


L.append('== WINNERS vs LOSERS (median of each feature on the eve day; exit A) ==')
L.append('%-14s %10s %10s' % ('feature', 'winners', 'losers'))
for f, lab, _ in FEATS:
    L.append('%-14s %10.2f %10.2f   %s' % (f, med(win, f), med(los, f), lab))
L.append('')
L.append('== EACH FEATURE BUCKET (exit A) ==')
hdr = '%-9s %-10s %6s %4s %7s %5s %7s | ' % ('feature', 'bucket', 'n', 'win', 'avgR', 'PF', 'avgR_B') + ' '.join('%6d' % y for y in years)
brows = []
for fi, (f, lab, e) in enumerate(FEATS):
    L.append('-- %s (%s)' % (f, lab)); L.append(hdr)
    for k in range(-1, len(e) + 1):
        rows = [t for t in T if t['b'][fi] == k]
        if len(rows) < 100: continue
        n, w, a, pf = stats(rows); _, _, ab, _ = stats(rows, 'rb')
        yr = []
        for y in years:
            yv = [t['ra'] for t in rows if t['year'] == y]
            yr.append(sum(yv) / len(yv) if len(yv) >= 30 else float('nan'))
        L.append('%-9s %-10s %6d %4d %7.3f %5.2f %7.3f | ' % (f, blabel(e, k), n, w, a, pf, ab) + ' '.join('%6.3f' % v for v in yr))
        brows.append(dict(feature=f, bucket=blabel(e, k), n=n, win=w, avgR_A=round(a, 3), pf_A=round(pf, 2), avgR_B=round(ab, 3)))
    L.append('')
with open(os.path.join(out_dir, 'pattern_buckets.csv'), 'w', newline='', encoding='utf-8') as h:
    wr = csv.DictWriter(h, fieldnames=list(brows[0].keys())); wr.writeheader(); wr.writerows(brows)

# pair combos: discover on TRAIN, confirm on TEST
acc = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0.0, 0])      # n_tr, sum_tr, win_tr, n_te, sum_te, win_te
nf = len(FEATS)
for t in T:
    tr_ = t['year'] <= TRAIN_END; r = t['ra']; b = t['b']
    for x in range(nf):
        bx = b[x]
        if bx < 0: continue
        for y in range(x + 1, nf):
            by = b[y]
            if by < 0: continue
            a_ = acc[(x, bx, y, by)]
            if tr_:
                a_[0] += 1; a_[1] += r; a_[2] += (r > 0)
            else:
                a_[3] += 1; a_[4] += r; a_[5] += (r > 0)
cand = [(k, v) for k, v in acc.items() if v[0] >= 150 and v[3] >= 60]
cand.sort(key=lambda kv: -kv[1][1] / kv[1][0])
L.append('== BEST 2-FEATURE COMBOS found on TRAIN (<= %d), then re-checked on TEST (> %d). n_tr>=150, n_te>=60 ==' % (TRAIN_END, TRAIN_END))
L.append('%-52s %6s %4s %7s | %6s %4s %7s' % ('combo', 'n_tr', 'win', 'avgR', 'n_te', 'win', 'avgR'))
crow = []; held = 0; top = cand[:30]
for (x, bx, y, by), v in top:
    lab = '%s %s + %s %s' % (FEATS[x][0], blabel(FEATS[x][2], bx), FEATS[y][0], blabel(FEATS[y][2], by))
    atr_ = v[1] / v[0]; ate = v[4] / v[3]
    held += ate > 0
    L.append('%-52s %6d %4d %7.3f | %6d %4d %7.3f' % (lab, v[0], round(100.0 * v[2] / v[0]), atr_, v[3], round(100.0 * v[5] / v[3]), ate))
for (x, bx, y, by), v in cand[:300]:
    crow.append(dict(combo='%s %s + %s %s' % (FEATS[x][0], blabel(FEATS[x][2], bx), FEATS[y][0], blabel(FEATS[y][2], by)),
                     n_train=v[0], avgR_train=round(v[1] / v[0], 3), n_test=v[3], avgR_test=round(v[4] / v[3], 3)))
with open(os.path.join(out_dir, 'pattern_combos.csv'), 'w', newline='', encoding='utf-8') as h:
    wr = csv.DictWriter(h, fieldnames=list(crow[0].keys())) if crow else None
    if wr: wr.writeheader(); wr.writerows(crow)
L.append('')
L.append('Of the top %d train combos, %d were still profitable on the TEST years. Candidates tested: %d (many tries = some look good by luck).' % (
    len(top), held, len(cand)))
allte = [v[4] / v[3] for _, v in cand]
L.append('Average test avgR across ALL %d candidate combos (luck level): %.3f' % (len(cand), sum(allte) / len(allte) if allte else 0))
L.append('Trust only patterns that (1) are profitable in most years in the bucket table and (2) stay profitable on TEST. Past results do not guarantee future results.')
open(os.path.join(out_dir, 'pattern_summary.txt'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
