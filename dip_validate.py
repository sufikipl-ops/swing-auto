# Out-of-sample check of the DIP setup improvements. usage: python dip_validate.py <bhav_folder> <out_folder> -> dip_validate_summary.txt
# Same base signals/features as dip_enh.py. Filters/pairs/scores are CHOSEN on TRAIN years (<= 2024) and then JUDGED on TEST years (2025+).
# Base signal = Dip Tier A (3-day drop <= -8%) or Tier B (-5..-8% and market breadth >= 50%), uptrend (U2). Entry next open, stop 2 ATR,
# exit at close of day 5 (or day 10 column), cost 0.25%, skip gap > +1.5% / < -3%. Each feature is tested as a FILTER on that base set.
import csv, glob, os, sys, datetime, collections, itertools

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
COST = 0.0025
THR = float(os.environ.get('DIP_THR', '-0.05'))
MIN_N = int(os.environ.get('MIN_N', '150'))


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
        else:
            au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
        n += 1
        if n >= 14: out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


def adx_at(hi, lo, cl, i, n=14):
    s = max(1, i - 80)
    pdm, mdm, trl = [], [], []
    for k in range(s, i + 1):
        up = hi[k] - hi[k - 1]; dn = lo[k - 1] - lo[k]
        pdm.append(up if (up > dn and up > 0) else 0.0); mdm.append(dn if (dn > up and dn > 0) else 0.0)
        trl.append(max(hi[k] - lo[k], abs(hi[k] - cl[k - 1]), abs(lo[k] - cl[k - 1])))
    if len(trl) < 2 * n:
        return None
    def wil(v):
        t = sum(v[:n]); out = [t]
        for x in v[n:]:
            t = t - t / n + x; out.append(t)
        return out
    st, sp, sm = wil(trl), wil(pdm), wil(mdm)
    dx = []
    for a, b, c in zip(st, sp, sm):
        if a == 0: dx.append(0.0); continue
        p, m = 100.0 * b / a, 100.0 * c / a
        dx.append(0.0 if p + m == 0 else 100.0 * abs(p - m) / (p + m))
    adx = sum(dx[:n]) / n
    for v in dx[n:]:
        adx = (adx * (n - 1) + v) / n
    return adx


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
            t = [num(r[k]) for k in (4, 5, 6, 8, 10, 11)]
            if None in t: continue
            data[r[0].strip()][d] = tuple(t) + (num(r[14]),)
if not data:
    print('no data'); sys.exit(1)
alldates = sorted({d for v in data.values() for d in v})
print('symbols', len(data), 'dates', alldates[0], alldates[-1], len(alldates))

above = collections.Counter(); total = collections.Counter()
sigs = []
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 130: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]; cl = [byd[d][3] for d in ds]
    vol = [byd[d][4] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]; dl = [byd[d][6] for d in ds]
    e20 = ema(cl, 20); e50 = ema(cl, 50); rs = rsi_series(cl)
    e12 = ema(cl, 12); e26 = ema(cl, 26); macd = [a - b for a, b in zip(e12, e26)]; msig = ema(macd, 9)
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    bp = 0; last_bad = -10 ** 9
    for i in range(60, n):
        d = ds[i]; total[d] += 1
        if cl[i] > e50[i]: above[d] += 1
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]; bp += 1
        if last_bad > i - 90 or i + 12 >= n: continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5 or cl[i] > 6000: continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / cl[i] < 0.004: continue
        ret3 = cl[i] / cl[i - 3] - 1
        if ret3 > THR: continue
        ret60 = cl[i] / cl[i - 60] - 1
        if not (cl[i] > e50[i] and e20[i] > e50[i] and e50[i] > e50[i - 10] and ret60 > 0 and rs[i] is not None and rs[i] < 45): continue
        # outcome (next open entry)
        j = i + 1
        if op[j] > cl[i] * 1.015 or op[j] < cl[i] * 0.97: continue
        entry = op[j]; risk = 2.0 * atr; stop = entry - risk
        res = {}
        for hold in (5, 10):
            end = j + hold; ex = None
            for k in range(j, end):
                if k > j and op[k] <= stop: ex = op[k]; break
                if lo[k] <= stop: ex = stop; break
            if ex is None: ex = cl[end - 1]
            res[hold] = (ex - entry) / risk - COST * entry / risk
        # features
        rng = hi[i] - lo[i]; body = abs(cl[i] - op[i])
        lw = min(cl[i], op[i]) - lo[i]; uw = hi[i] - max(cl[i], op[i])
        sma20 = sum(cl[i - 19:i + 1]) / 20.0
        sd = (sum((x - sma20) ** 2 for x in cl[i - 19:i + 1]) / 20.0) ** 0.5
        L = min(lo[i - 40:i + 1]); H = max(hi[i - 40:i + 1])
        retr = (H - cl[i]) / (H - L) if H > L else None
        avgv = sum(vol[i - 20:i]) / 20.0
        dla = [x for x in dl[i - 20:i] if x is not None]
        dla = sum(dla) / len(dla) if dla else None
        sma200 = sum(cl[i - 199:i + 1]) / 200.0 if i >= 199 else None
        adx = adx_at(hi, lo, cl, i)
        mh = macd[i] - msig[i]
        F = {
            'bull_candle (close>open)': cl[i] > op[i],
            'red_candle (close<open)': cl[i] < op[i],
            'close_in_upper_half': rng > 0 and (cl[i] - lo[i]) / rng >= 0.5,
            'close_in_lower_quarter': rng > 0 and (cl[i] - lo[i]) / rng <= 0.25,
            'hammer (lower wick>=2x body)': body > 0 and lw >= 2 * body and uw <= body,
            'bullish_engulfing': i > 0 and cl[i - 1] < op[i - 1] and cl[i] > op[i] and cl[i] >= op[i - 1] and op[i] <= cl[i - 1],
            'last_day_up (close>prev close)': cl[i] > cl[i - 1],
            'last_day_down (close<prev close)': cl[i] < cl[i - 1],
            'signal_day_gap_down >2%': op[i] < cl[i - 1] * 0.98,
            'RVOL>=1.5': avgv > 0 and vol[i] / avgv >= 1.5,
            'RVOL<1.0': avgv > 0 and vol[i] / avgv < 1.0,
            'delivery>=20d_avg': (dl[i] is not None and dla is not None and dl[i] >= dla),
            'delivery<20d_avg': (dl[i] is not None and dla is not None and dl[i] < dla),
            'close_below_BB_lower(20,2)': sd > 0 and cl[i] <= sma20 - 2 * sd,
            'above_SMA200': (sma200 is not None and cl[i] > sma200) if sma200 is not None else None,
            'fib_retr<38.2%': retr is not None and retr < 0.382,
            'fib_retr_38.2-61.8%': retr is not None and 0.382 <= retr <= 0.618,
            'fib_retr>61.8%': retr is not None and retr > 0.618,
            'ADX>=25': adx is not None and adx >= 25,
            'ADX<20': adx is not None and adx < 20,
            'MACD_hist<0': mh < 0,
            'MACD_hist>=0': mh >= 0,
            'near_EMA50 (close<=1.05xEMA50)': cl[i] <= e50[i] * 1.05,
            'far_EMA50 (close>1.05xEMA50)': cl[i] > e50[i] * 1.05,
            'RSI<35': rs[i] < 35,
            'RSI35-45': rs[i] >= 35,
        }
        sigs.append((d, ret3, F, res))
print('base signals', len(sigs))
if not sigs:
    sys.exit(1)


TRAIN_END = 2024
MIN_TR = int(os.environ.get('MIN_TR', '100'))
MIN_TE = int(os.environ.get('MIN_TE', '40'))
years = sorted({s[0].year for s in sigs})


def tier_ok(s, which):
    d, ret3 = s[0], s[1]
    b = above[d] / float(total[d]) if total[d] else 0
    a = ret3 <= -0.08
    bb = (-0.08 < ret3 <= -0.05) and b >= 0.5
    return (a or bb) if which == 'AB' else a


def st(sel, hold):
    v = [x[3][hold] for x in sel]; n = len(v)
    if not n: return (0, 0, 0.0, 0.0)
    gp = sum(x for x in v if x > 0); gl = -sum(x for x in v if x < 0)
    return (n, round(100.0 * sum(1 for x in v if x > 0) / n), sum(v) / n, (gp / gl if gl > 0 else 9.99))


def split(sel):
    return [x for x in sel if x[0].year <= TRAIN_END], [x for x in sel if x[0].year > TRAIN_END]


def fmt(n, w, a, pf):
    return '%5d %3d%% %7.3f %5.2f' % (n, w, a, pf)


L = ['DIP VALIDATION (generated %s)' % datetime.date.today().isoformat(),
     'Data %s to %s. Base = Dip Tier A (<= -8%% in 3d) or Tier B (-5..-8%% & breadth>=50%%), uptrend. Entry next open, stop 2 ATR, hold N days, cost 0.25%%.' % (alldates[0], alldates[-1]),
     'TRAIN = years <= %d (choose filters here). TEST = years > %d (judge here; filters never saw it).' % (TRAIN_END, TRAIN_END), '']
verdict = []
for which, title in (('AB', 'Tier A + B'), ('A', 'Tier A only')):
    base = [x for x in sigs if tier_ok(x, which)]
    for hold in (5, 10):
        tr_, te_ = split(base)
        L.append('==== %s | hold %d days ====' % (title, hold))
        L.append('%-40s | %-23s | %-23s' % ('', 'TRAIN n win avgR PF', 'TEST n win avgR PF'))
        L.append('%-40s | %s | %s' % ('BASE (no filter)', fmt(*st(tr_, hold)), fmt(*st(te_, hold))))
        feats = sorted({k for x in base for k, v in x[2].items() if v is not None})
        singles = []
        for k in feats:
            a_, b_ = [x for x in tr_ if x[2].get(k) is True], [x for x in te_ if x[2].get(k) is True]
            sa, sb = st(a_, hold), st(b_, hold)
            if sa[0] >= MIN_TR and sb[0] >= MIN_TE: singles.append((k, sa, sb))
        L.append('-- single filters (n_train>=%d, n_test>=%d)' % (MIN_TR, MIN_TE) + ', sorted by TRAIN avgR --')
        for k, sa, sb in sorted(singles, key=lambda t: -t[1][2]):
            L.append('%-40s | %s | %s' % (k[:40], fmt(*sa), fmt(*sb)))
        # pairs
        pairs = []
        for a, c in itertools.combinations(feats, 2):
            a_ = [x for x in tr_ if x[2].get(a) is True and x[2].get(c) is True]
            b_ = [x for x in te_ if x[2].get(a) is True and x[2].get(c) is True]
            sa, sb = st(a_, hold), st(b_, hold)
            if sa[0] >= MIN_TR and sb[0] >= MIN_TE: pairs.append((a + ' + ' + c, sa, sb))
        pairs.sort(key=lambda t: -t[1][2])
        L.append('-- best PAIRS chosen on TRAIN (n_train>=%d, n_test>=%d)' % (MIN_TR, MIN_TE) + ': %d candidates --' % len(pairs))
        for k, sa, sb in pairs[:12]:
            L.append('%-40s | %s | %s' % (k[:40], fmt(*sa), fmt(*sb)))
        if pairs:
            held = sum(1 for k, sa, sb in pairs[:12] if sb[2] > 0)
            allte = [sb[2] for _, _, sb in pairs]
            L.append('Top-12 train pairs still profitable on TEST: %d/12. Average TEST avgR over ALL %d pairs (luck level): %.3f; base TEST avgR %.3f' % (
                held, len(pairs), sum(allte) / len(allte), st(te_, hold)[2]))
        # score: count of train-selected single filters passed
        sel = [k for k, sa, sb in sorted(singles, key=lambda t: -t[1][2]) if sa[2] > st(tr_, hold)[2] + 0.02 and sa[0] >= int(MIN_TR * 1.5)][:5]
        L.append('-- SCORE = how many of these TRAIN-selected filters pass: %s --' % ', '.join(sel))
        if sel:
            L.append('%-40s | %-23s | %-23s' % ('score', 'TRAIN n win avgR PF', 'TEST n win avgR PF'))
            for lo_ in range(0, len(sel) + 1):
                a_ = [x for x in tr_ if sum(1 for k in sel if x[2].get(k) is True) == lo_]
                b_ = [x for x in te_ if sum(1 for k in sel if x[2].get(k) is True) == lo_]
                L.append('%-40s | %s | %s' % ('passes %d of %d' % (lo_, len(sel)), fmt(*st(a_, hold)), fmt(*st(b_, hold))))
            for need in range(2, len(sel) + 1):
                a_ = [x for x in tr_ if sum(1 for k in sel if x[2].get(k) is True) >= need]
                b_ = [x for x in te_ if sum(1 for k in sel if x[2].get(k) is True) >= need]
                L.append('%-40s | %s | %s' % ('passes >= %d of %d' % (need, len(sel)), fmt(*st(a_, hold)), fmt(*st(b_, hold))))
                yy = ' '.join('%d:%.2f(n%d)' % (y, (lambda v: sum(v) / len(v) if v else 0.0)([x[3][hold] for x in base if x[0].year == y and sum(1 for k in sel if x[2].get(k) is True) >= need]),
                              len([x for x in base if x[0].year == y and sum(1 for k in sel if x[2].get(k) is True) >= need])) for y in years)
                L.append('      per year (all years, passes >= %d): %s' % (need, yy))
        L.append('')
L.append('How to read: a filter/score is real only if TEST avgR stays clearly positive and above BASE TEST. Many tries => luck is possible.')
L.append('Past results do not guarantee future results. Not financial advice.')
open(os.path.join(out_dir, 'dip_validate_summary.txt'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
