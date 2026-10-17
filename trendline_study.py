# Trendline break study (owner's reference video, both directions), daily bhavcopy ~4 saal, liquid stocks.
# LONG: girti trendline (>=3 swing highs, line ke upar koi close nahi) ke upar close -> agle din open par buy.
# SHORT: chadhti trendline (>=3 swing lows) ke neeche close -> agle din open par sell (sirf jaankari: cash me
#        overnight short nahi hota, futures chahiye).
# Filters: SWEEP (pichhle 10 din me barabar lows/highs ke paar jaake wapas aaya), TREND (EMA50 disha me).
# Stops: ATR (1.5 ATR) ya STRUCT (breakout candle ka low/high, min 0.5 ATR). Targets 2R/3R/4R, max 10 din.
# Next-day OPEN entry, gap filter, cost 0.25%, same-bar stop+target = stop. TRAIN <= 2024, TEST 2025+.
# usage: python trendline_study.py <bhav_folder> <out_folder> -> trendline_summary.txt, trendline_results.csv
import csv, glob, os, sys, datetime, collections

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
COST = 0.25 / 100.0
GAP = 0.015
PIV = 3                 # swing high/low: 3 din aage-peeche se uncha/neecha (3 din baad pakka hota hai)
LOOK = 80               # trendline kitne din peeche tak
TOUCH = 0.35            # line ko 'chhuna' = 0.35 ATR ke andar
HOLD = 10
STOPS = ['ATR1.5', 'STRUCT']
TGTS = [2.0, 3.0, 4.0]
MIN_TRAIN, MIN_TEST = 100, 40


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
print('symbols', len(data), 'dates', alldates[0], alldates[-1], len(alldates), flush=True)


def sim(op, hi, lo, cl, i, n, side, risk_abs, stop_px, tgt):
    j = i + 1
    if j >= n: return None
    if side == 1 and (op[j] > cl[i] * (1 + GAP) or op[j] < cl[i] * (1 - 2 * GAP)): return None
    if side == -1 and (op[j] < cl[i] * (1 - GAP) or op[j] > cl[i] * (1 + 2 * GAP)): return None
    entry = op[j]
    if stop_px is None:
        stop = entry - side * risk_abs
    else:
        stop = stop_px
    risk = (entry - stop) * side
    if risk <= 0: return None
    target = entry + side * tgt * risk
    end = min(j + HOLD, n)
    if end - j < HOLD: return None
    ex = None
    for k in range(j, end):
        if k > j and (op[k] - stop) * side <= 0: ex = op[k]; break
        if (side == 1 and lo[k] <= stop) or (side == -1 and hi[k] >= stop): ex = stop; break
        if (side == 1 and hi[k] >= target) or (side == -1 and lo[k] <= target): ex = target; break
    if ex is None: ex = cl[end - 1]
    return (ex - entry) * side / risk - COST * entry / risk


def best_line(piv, vals, i, atr, cl, side):
    """piv: confirmed pivot indexes (<= i-PIV) in LOOK window. side=1: falling line over highs (long break);
    side=-1: rising line under lows (short break). Returns line value at i or None."""
    best = None
    P = [p for p in piv if p >= i - LOOK]
    for b in range(len(P) - 1, 0, -1):
        p2 = P[b]
        for a in range(b - 1, -1, -1):
            p1 = P[a]
            if p2 - p1 < 5: continue
            if side == 1 and not vals[p1] > vals[p2]: continue          # lower highs
            if side == -1 and not vals[p1] < vals[p2]: continue         # higher lows
            slope = (vals[p2] - vals[p1]) / (p2 - p1)
            line = lambda t: vals[p1] + slope * (t - p1)
            ok = True
            for t in range(p1, i):                                      # beech me line ke paar koi close nahi
                if (cl[t] - line(t)) * side > 0.1 * atr:
                    ok = False; break
            if not ok: continue
            touches = sum(1 for p in P if p1 <= p <= p2 and abs(vals[p] - line(p)) <= TOUCH * atr)
            if touches >= 3 and (best is None or touches > best[0]):
                best = (touches, line(i), line(i - 1))
        if best: break                                                   # sabse naya valid line
    return best


rows_raw = collections.defaultdict(list)
base = collections.defaultdict(list)
nsym = 0
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 150: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]
    cl = [byd[d][3] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    e50 = ema(cl, 50)
    ph = [i for i in range(PIV, n - PIV) if hi[i] == max(hi[i - PIV:i + PIV + 1])]
    pl = [i for i in range(PIV, n - PIV) if lo[i] == min(lo[i - PIV:i + PIV + 1])]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]; bp = 0; last_bad = -10 ** 9
    hp = lp = 0
    nsym += 1
    for i in range(100, n - HOLD - 1):
        while bp < len(bad) and bad[bp] <= i: last_bad = bad[bp]; bp += 1
        if last_bad > i - 90: continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5 or cl[i] > 6000: continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / cl[i] < 0.004: continue
        d = ds[i]
        if i % 5 == 0:
            for t_ in TGTS:
                r_ = sim(op, hi, lo, cl, i, n, 1, 1.5 * atr, None, t_)
                if r_ is not None: base[('LONG', t_)].append((d, r_))
        cph = [p for p in ph if p <= i - PIV and p >= i - LOOK]          # sirf pakke pivots (no lookahead)
        cpl = [p for p in pl if p <= i - PIV and p >= i - LOOK]
        for side, piv, vals in ((1, cph, hi), (-1, cpl, lo)):
            if len(piv) < 3: continue
            if side == 1 and not (cl[i] > cl[i - 1]): continue
            if side == -1 and not (cl[i] < cl[i - 1]): continue
            bl = best_line(piv, vals, i, atr, cl, side)
            if not bl: continue
            _, li, li1 = bl
            if not ((cl[i] - li) * side > 0.1 * atr and (cl[i - 1] - li1) * side <= 0.1 * atr): continue
            # SWEEP: pichhle 10 din me purane swing low (long) / high (short) ke paar gaya aur wapas band hua
            sweep = False
            if side == 1:
                old = [lo[p] for p in cpl if p < i - 10]
                if old:
                    lvl = min(old[-3:])
                    sweep = any(lo[k] < lvl and cl[k] > lvl for k in range(i - 10, i + 1))
            else:
                old = [hi[p] for p in cph if p < i - 10]
                if old:
                    lvl = max(old[-3:])
                    sweep = any(hi[k] > lvl and cl[k] < lvl for k in range(i - 10, i + 1))
            trend = (cl[i] > e50[i] and e50[i] > e50[i - 10]) if side == 1 else (cl[i] < e50[i] and e50[i] < e50[i - 10])
            filt = ['ANY'] + (['SWEEP'] if sweep else []) + (['TREND'] if trend else []) + (['SWEEP+TREND'] if sweep and trend else [])
            for st in STOPS:
                for t_ in TGTS:
                    if st == 'ATR1.5':
                        r_ = sim(op, hi, lo, cl, i, n, side, 1.5 * atr, None, t_)
                    else:
                        sp = lo[i] if side == 1 else hi[i]
                        # minimum 0.5 ATR door (bahut chhota SL = costs kha jaate)
                        sp = min(sp, cl[i] - 0.5 * atr) if side == 1 else max(sp, cl[i] + 0.5 * atr)
                        r_ = sim(op, hi, lo, cl, i, n, side, None, sp, t_)
                    if r_ is None: continue
                    for fl in filt:
                        rows_raw[('LONG' if side == 1 else 'SHORT', fl, st, t_)].append((d, r_))
print('symbols used', nsym, flush=True)


def agg(v):
    n = len(v)
    if not n: return dict(n=0, avg=0.0, pf=0.0, win=0)
    x = [r for _, r in v]; gp = sum(r for r in x if r > 0); gl = -sum(r for r in x if r < 0)
    return dict(n=n, avg=sum(x) / n, pf=gp / gl if gl else 9.99, win=round(100.0 * sum(1 for r in x if r > 0) / n))


years = sorted({d.year for d in alldates})
rows = []
for (side, fl, st, t_), v in rows_raw.items():
    a = agg(v); tr_ = agg([p for p in v if p[0].year <= 2024]); te = agg([p for p in v if p[0].year > 2024])
    yr = {y: agg([p for p in v if p[0].year == y]) for y in years}
    rows.append(dict(side=side, filter=fl, stop=st, target=t_, n=a['n'], win=a['win'], avgR=round(a['avg'], 3), pf=round(a['pf'], 2),
                     n_train=tr_['n'], trainR=round(tr_['avg'], 3), n_test=te['n'], testR=round(te['avg'], 3), test_win=te['win'],
                     **{'y%d' % y: (round(yr[y]['avg'], 3) if yr[y]['n'] >= 30 else '') for y in years}))
if rows:
    with open(os.path.join(out_dir, 'trendline_results.csv'), 'w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
L = ['TRENDLINE BREAK STUDY (generated %s)' % datetime.date.today(),
     'Data %s to %s. Trendline = >=3 swing highs/lows (3-din pivot), %d din tak, beech me koi close paar nahi. Entry next open, cost 0.25%%, max %d din.' % (alldates[0], alldates[-1], LOOK, HOLD),
     'SHORT sirf jaankari: cash me 2-5 din ka short nahi hota (futures chahiye). TRAIN = 2024 tak, TEST = 2025+.', '']
for t_ in TGTS:
    b = agg(base[('LONG', t_)]); bt = agg([p for p in base[('LONG', t_)] if p[0].year > 2024])
    L.append('BASE random liquid LONG, 1.5 ATR stop, %gR: n %d avgR %.3f | test %.3f' % (t_, b['n'], b['avg'], bt['avg']))
L.append('')
hdr = '%-5s %-12s %-7s %4s %6s %4s %7s %5s | %5s %7s | %5s %7s %4s | %s' % ('side', 'filter', 'stop', 'tgt', 'n', 'win', 'avgR', 'PF', 'nTr', 'trainR', 'nTe', 'testR', 'tW', ' '.join('y%d' % y for y in years))
for side in ('LONG', 'SHORT'):
    L.append('== %s ==' % side); L.append(hdr)
    for r in sorted([r for r in rows if r['side'] == side], key=lambda r: (r['filter'], r['stop'], r['target'])):
        L.append('%-5s %-12s %-7s %4.1f %6d %3d%% %7.3f %5.2f | %5d %7.3f | %5d %7.3f %3d%% | %s' % (
            r['side'], r['filter'], r['stop'], r['target'], r['n'], r['win'], r['avgR'], r['pf'], r['n_train'], r['trainR'], r['n_test'], r['testR'], r['test_win'],
            ' '.join(str(r['y%d' % y]) for y in years)))
    L.append('')
ok = [r for r in rows if r['n_train'] >= MIN_TRAIN and r['n_test'] >= MIN_TEST and r['trainR'] > 0 and r['testR'] > 0]
L.append('TRAIN aur TEST dono me plus (n_train>=%d, n_test>=%d): %d of %d' % (MIN_TRAIN, MIN_TEST, len(ok), len(rows)))
for r in sorted(ok, key=lambda r: -r['testR'])[:12]:
    L.append('  %s %s %s %gR: train %.3f (n %d), test %.3f (n %d, win %d%%)' % (r['side'], r['filter'], r['stop'], r['target'], r['trainR'], r['n_train'], r['testR'], r['n_test'], r['test_win']))
L.append('Bahut combos dekhe: chhota plus luck ho sakta hai. Past results do not guarantee future results.')
open(os.path.join(out_dir, 'trendline_summary.txt'), 'w').write('\n'.join(L) + '\n')
print('\n'.join(L))
