# Market regime study: kaunsa setup kis market haal (tezi / mixed / kamzor / bahut kamzor) me chalta hai.
# Regime = us din liquid stocks me se kitne % EMA50 ke upar (breadth). 4 saal ke SAARE kamzor din ek saath dekhe jaate
# hain (2022 ka hissa, 2025, 2026), sirf ek saal nahi -> zyada data, kam kismat. Har setup har regime me alag saalon me
# bhi tika ho tabhi maana jaata hai.
# Honest rules: next-day OPEN entry, cost 0.25%, gap-up >1.5% / gap-down >3% skip, same-bar stop+target = stop,
# 90 din split/bonus skip. Long only (cash me 2-5 din short nahi hota).
# usage: python regime_study.py <bhav_folder> <out_folder> -> regime_summary.txt, regime_results.csv, docs/regime.json
import csv, glob, os, sys, json, datetime, collections, bisect

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
COST = 0.25 / 100.0
GAP_UP, GAP_DN = 1.015, 0.97
EXITS = [('2ATR/5d', 2.0, 5, None), ('2ATR/3d', 2.0, 3, None), ('1.5ATR/10d/T2R', 1.5, 10, 2.0)]
REGIMES = [('STRONG', 60, 101), ('MIXED', 40, 60), ('WEAK', 25, 40), ('VWEAK', -1, 25)]
SETUPS = ['DIP_A', 'DIP_B', 'BREAKOUT', 'PULLBACK', 'RS_LEADER', 'HIGH52', 'OVERSOLD_BOUNCE', 'DEEP_OVERSOLD', 'STRUCT', 'STRUCT_DEEP']
DESC = {'DIP_A': 'Uptrend stock 3 din me 8%+ gira (hamara Dip A)', 'DIP_B': 'Uptrend stock 3 din me 5-8% gira (Dip B)',
        'BREAKOUT': '20-din high ke upar band, volume 1.5x+', 'PULLBACK': 'Uptrend stock EMA20 tak aaya',
        'RS_LEADER': 'Market ka leader: 60-din return top 10%, EMA50 upar, high ke paas',
        'HIGH52': 'Naya 52-hafte high par band', 'OVERSOLD_BOUNCE': 'Downtrend stock, RSI<30, 3 din me 8%+ gira (bounce)',
        'DEEP_OVERSOLD': 'RSI<25 aur 10 din me 15%+ gira (gehra oversold bounce)',
        'STRUCT': 'Market structure: higher high + higher low, retracement (38%+) ke baad chhota high toota (expansion shuru)',
        'STRUCT_DEEP': 'Wahi structure setup, par retracement gehra (61.8%+, pichhle higher low ke upar)',
        'STRUCT_ALL': 'Structure setup (STRUCT + STRUCT_DEEP dono)'}
SWING_EXIT = 'SwingSL/10d/T2R'     # structure setups ka apna exit: SL retracement low ke neeche, target 2R, max 10 din
MIN_N, MIN_YEARS = 100, 2


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


def rsi_series(cl):
    out = [None] * len(cl); au = ad = None; n = 0
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]; up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None: au, ad = up, dn
        else: au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
        n += 1
        if n >= 14: out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


data = collections.defaultdict(dict)
for f in sorted(glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv'))):
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


def sim_px(op, hi, lo, cl, i, n, stop_px, hold, tgt):
    """Jaise sim, par SL ek fix bhav (swing low) par. Risk bahut chhota/bada ho to skip."""
    j = i + 1
    if j >= n or op[j] > cl[i] * GAP_UP or op[j] < cl[i] * GAP_DN: return None
    entry = op[j]; risk = entry - stop_px
    if risk <= entry * 0.01 or risk > entry * 0.15: return None
    target = entry + tgt * risk; end = min(j + hold, n)
    if end - j < hold: return None
    ex = None
    for k in range(j, end):
        if k > j and op[k] <= stop_px: ex = op[k]; break
        if lo[k] <= stop_px: ex = stop_px; break
        if hi[k] >= target: ex = target; break
    if ex is None: ex = cl[end - 1]
    return (ex - entry) / risk - COST * entry / risk


def struct_sig(hi, lo, cl, i, PH, PL, fired):
    """Fractal swing points (2 din dono taraf, i-2 tak pakke). Uptrend: aakhri 2 swing high upar-upar, swing low bhi.
    Aakhri pivot = swing high (expansion ka top), uske baad retracement jo pichhla higher low nahi toda,
    aur aaj close retracement ke dauraan bane chhote high ke upar (chhota dhaancha upar muda). Return (name, swing_low) ya None."""
    a_, b_ = bisect.bisect_right(PH, i - 2), bisect.bisect_right(PL, i - 2)
    hs = PH[max(0, a_ - 2):a_]; ls = PL[max(0, b_ - 2):b_]
    if len(hs) < 2 or len(ls) < 2: return None
    h1, h2 = hs; l1, l2 = ls
    if not (hi[h2] > hi[h1] and lo[l2] > lo[l1] and l2 < h2 and h1 < l2): return None
    if h2 in fired or h2 >= i - 1: return None
    seg = range(h2 + 1, i)
    k = min(seg, key=lambda x: lo[x]); m = lo[k]
    if m <= lo[l2] or i - k > 6 or k >= i: return None
    leg = hi[h2] - lo[l2]
    depth = (hi[h2] - m) / leg if leg > 0 else 0
    if depth < 0.382: return None
    mh = max(hi[k:i])
    if not (cl[i] > mh and cl[i - 1] <= mh and cl[i] < hi[h2]): return None
    fired.add(h2)
    return ('STRUCT_DEEP' if depth >= 0.618 else 'STRUCT', m)


# ---- pass 1: series, liquidity, breadth, cross-sectional 60d return rank
S = {}
above = collections.Counter(); tot = collections.Counter(); r60 = collections.defaultdict(list)
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 130: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]
    cl = [byd[d][3] for d in ds]; vo = [byd[d][4] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    e50 = ema(cl, 50)
    liq = [False] * n; atr = [None] * n
    for i in range(60, n):
        atr[i] = sum(tr[i - 13:i + 1]) / 14.0
        to20 = sum(to[i - 20:i]) / 20.0
        liq[i] = to20 >= 5 and cl[i] <= 6000 and atr[i] / cl[i] >= 0.004
        if liq[i]:
            tot[ds[i]] += 1; above[ds[i]] += cl[i] > e50[i]
            r60[ds[i]].append(cl[i] / cl[i - 60] - 1)
    S[sym] = (ds, op, hi, lo, cl, vo, atr, liq, e50)
BR = {d: 100.0 * above[d] / tot[d] for d in tot if tot[d] >= int(os.environ.get('MIN_UNIVERSE', '50'))}
if not BR:
    print('breadth nahi bana (universe chhota)'); sys.exit(1)
R60TOP = {}
for d, v in r60.items():
    v.sort(); R60TOP[d] = v[int(0.9 * len(v))] if v else 9e9
bd = sorted(BR)


def regime_of(b):
    for name, lo_, hi_ in REGIMES:
        if lo_ <= b < hi_: return name
    return 'STRONG'
REG = {d: regime_of(BR[d]) for d in bd}
print('breadth days', len(bd), flush=True)

# ---- pass 2: signals
res = collections.defaultdict(list)          # (setup, regime, exit) -> [(date, R)]
base = collections.defaultdict(list)         # (regime, exit) -> [(date, R)]
for sym, (ds, op, hi, lo, cl, vo, atr, liq, e50) in S.items():
    n = len(ds); e20 = ema(cl, 20); rs = rsi_series(cl)
    PH = [p for p in range(2, n - 2) if hi[p] > max(hi[p - 2:p]) and hi[p] >= max(hi[p + 1:p + 3])]
    PL = [p for p in range(2, n - 2) if lo[p] < min(lo[p - 2:p]) and lo[p] <= min(lo[p + 1:p + 3])]
    fired = set()
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]; bp = 0; last_bad = -10 ** 9
    for i in range(70, n - 11):
        while bp < len(bad) and bad[bp] <= i: last_bad = bad[bp]; bp += 1
        if last_bad > i - 90 or not liq[i]: continue
        d = ds[i]; rg = REG.get(d)
        if not rg: continue
        R = None
        if i % 5 == 0:
            R = [sim(op, hi, lo, cl, i, n, atr[i], e[1], e[2], e[3]) for e in EXITS]
            for k, r_ in enumerate(R):
                if r_ is not None: base[(rg, k)].append((d, r_))
        up = cl[i] > e50[i] and e20[i] > e50[i] and e50[i] > e50[i - 10]
        ret3 = cl[i] / cl[i - 3] - 1; ret10 = cl[i] / cl[i - 10] - 1
        av20 = sum(vo[i - 20:i]) / 20.0
        sig = []
        if up and ret3 <= -0.08: sig.append('DIP_A')
        if up and -0.08 < ret3 <= -0.05: sig.append('DIP_B')
        if cl[i] > max(hi[i - 20:i]) and av20 > 0 and vo[i] >= 1.5 * av20 and cl[i] > e50[i]: sig.append('BREAKOUT')
        if up and lo[i] <= e20[i] * 1.005 and cl[i] >= e20[i] * 0.98: sig.append('PULLBACK')
        if cl[i] > e50[i] and (cl[i] / cl[i - 60] - 1) >= R60TOP.get(d, 9e9) and cl[i] >= 0.95 * max(hi[i - 19:i + 1]): sig.append('RS_LEADER')
        if i >= 250 and cl[i] >= max(hi[i - 250:i]): sig.append('HIGH52')
        if cl[i] < e50[i] and rs[i] is not None and rs[i] < 30 and ret3 <= -0.08: sig.append('OVERSOLD_BOUNCE')
        if rs[i] is not None and rs[i] < 25 and ret10 <= -0.15: sig.append('DEEP_OVERSOLD')
        st = struct_sig(hi, lo, cl, i, PH, PL, fired)
        if st:
            sig.append(st[0]); sig.append('STRUCT_ALL')
            r_ = sim_px(op, hi, lo, cl, i, n, st[1] * 0.998, 10, 2.0)
            if r_ is not None:
                res[(st[0], rg, len(EXITS))].append((d, r_)); res[('STRUCT_ALL', rg, len(EXITS))].append((d, r_))
        if not sig: continue
        if R is None: R = [sim(op, hi, lo, cl, i, n, atr[i], e[1], e[2], e[3]) for e in EXITS]
        for s_ in sig:
            for k, r_ in enumerate(R):
                if r_ is not None: res[(s_, rg, k)].append((d, r_))
print('signals done', flush=True)


def agg(v):
    n = len(v)
    if not n: return dict(n=0, avg=0.0, pf=0.0, win=0)
    x = [r for _, r in v]; gp = sum(r for r in x if r > 0); gl = -sum(r for r in x if r < 0)
    return dict(n=n, avg=sum(x) / n, pf=gp / gl if gl else 9.99, win=round(100.0 * sum(1 for r in x if r > 0) / n))


years = sorted({d.year for d in bd})
rows = []
for (s_, rg, k), v in res.items():
    a = agg(v); b = agg(base[(rg, min(k, len(EXITS) - 1))])
    yr = {y: agg([p for p in v if p[0].year == y]) for y in years}
    yrs = [y for y in years if yr[y]['n'] >= 20]
    pos = sum(1 for y in yrs if yr[y]['avg'] > 0)
    rows.append(dict(setup=s_, regime=rg, exit=EXITS[k][0] if k < len(EXITS) else SWING_EXIT, n=a['n'], win=a['win'], avgR=round(a['avg'], 3), pf=round(a['pf'], 2),
                     baseR=round(b['avg'], 3), edge=round(a['avg'] - b['avg'], 3), years_pos='%d/%d' % (pos, len(yrs)),
                     ok=a['n'] >= MIN_N and a['avg'] > 0 and pos >= MIN_YEARS and pos >= len(yrs) - 1,
                     **{'y%d' % y: (round(yr[y]['avg'], 3) if yr[y]['n'] >= 20 else '') for y in years},
                     **{'n%d' % y: yr[y]['n'] for y in years}))
with open(os.path.join(out_dir, 'regime_results.csv'), 'w', newline='') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

# ---- report
last = bd[-1]; cur = REG[last]; trend = BR[last] - BR[bd[-11]] if len(bd) > 11 else 0
days_by = collections.Counter((d.year, REG[d]) for d in bd)
L = ['MARKET REGIME STUDY (generated %s)' % datetime.date.today(),
     'Data %s to %s. Regime = liquid stocks me EMA50 ke upar ka %%: STRONG >=60, MIXED 40-60, WEAK 25-40, VWEAK <25.' % (alldates[0], alldates[-1]),
     'Entry next open, cost 0.25%%. ok = n>=%d, avgR>0, aur jin saalon me n>=20 unme se kam se kam %d (aur max 1 chhod ke sab) plus.' % (MIN_N, MIN_YEARS),
     'baseR = usi regime me random liquid stock (kuch na karo jaisa). edge = setup - base.', '',
     'AAJ (%s): breadth %.1f%% -> %s, 10 din me %+.1f points' % (last, BR[last], cur, trend), '',
     'Har saal har regime ke din:  ' + '  '.join('%d: %s' % (y, ' '.join('%s %d' % (rg, days_by[(y, rg)]) for rg, _, _ in REGIMES if days_by[(y, rg)])) for y in years), '']
for rg, _, _ in REGIMES:
    L.append('== %s ==' % rg)
    for k, e in enumerate(EXITS):
        b = agg(base[(rg, k)]); L.append('  BASE %-15s n %6d avgR %.3f' % (e[0], b['n'], b['avg']))
    L.append('  %-16s %-15s %6s %4s %7s %5s %7s %5s | %s' % ('setup', 'exit', 'n', 'win', 'avgR', 'PF', 'edge', 'yrs+', ' '.join('y%d' % y for y in years)))
    for r in sorted([r for r in rows if r['regime'] == rg], key=lambda r: -r['avgR']):
        if r['n'] < 30: continue
        L.append('  %-16s %-15s %6d %3d%% %7.3f %5.2f %7.3f %5s | %s%s' % (r['setup'], r['exit'], r['n'], r['win'], r['avgR'], r['pf'], r['edge'], r['years_pos'],
                 ' '.join(str(r['y%d' % y]) for y in years), '  <== OK' if r['ok'] else ''))
    L.append('')
best = {}
for rg, _, _ in REGIMES:
    ok = sorted([r for r in rows if r['regime'] == rg and r['ok']], key=lambda r: -r['avgR'])
    seen, picks = set(), []
    for r in ok:
        if r['setup'] in seen: continue
        seen.add(r['setup']); picks.append(r)
    best[rg] = picks[:4]
    L.append('%s me chalne wale setup: %s' % (rg, ', '.join('%s (%s, %+.2fR, n %d, %s saal plus)' % (r['setup'], r['exit'], r['avgR'], r['n'], r['years_pos']) for r in picks[:4]) or 'koi nahi (cash/chhota size behtar)'))
L.append('Past results do not guarantee future results. Bahut combos dekhe: chhota plus luck ho sakta hai.')
open(os.path.join(out_dir, 'regime_summary.txt'), 'w').write('\n'.join(L) + '\n')
print('\n'.join(L))
os.makedirs('docs', exist_ok=True)
json.dump({'updated': datetime.date.today().isoformat(), 'date': last.isoformat(), 'breadth': round(BR[last], 1), 'regime': cur,
           'trend10': round(trend, 1), 'desc': DESC,
           'best': {rg: [dict(setup=r['setup'], exit=r['exit'], avgR=r['avgR'], n=r['n'], win=r['win'], years_pos=r['years_pos'], baseR=r['baseR']) for r in best[rg]] for rg in best},
           'table': [dict(setup=r['setup'], regime=r['regime'], exit=r['exit'], avgR=r['avgR'], n=r['n'], win=r['win'], years_pos=r['years_pos'], ok=r['ok'])
                     for r in rows if r['exit'] == '2ATR/5d']},
          open('docs/regime.json', 'w'), separators=(',', ':'))
