# Do sawaal (paper trading 19-23 Oct: 23 Oct ko din ke beech jhatke ne saare SL kaat diye, phir bhav wapas aaya; app roz
# 100-200 "trade karo" deta hai jabki user din me 2 hi leta hai):
#   1) Stop-loss: din ke beech (abhi) vs CLOSE par (3:15 par dekho, close stop ke neeche ho tabhi becho) vs chauda stop.
#   2) Roz ke 2 kaise chunein: random, liquidity, kam/zyada ATR%, setup ki priority, sabse zyada gira, sabse kam RSI.
# Setups = app ke pass hue (paper.py jaise exit): VWEAK me OVERSOLD_BOUNCE / DEEP_OVERSOLD (5 din), DROP10 (3 din ya 20-din
# average), STRUCT / STRUCT_DEEP (SL swing low, 2R ya 10 din); Dip A (WEAK me, 5 din). Entry kal OPEN, gap +1.5%/-3% skip.
# R = (exit-entry)/(entry-stop) - kharcha 0.25%; har trade ka risk Rs500 maano to 1R = Rs500 (close-stop me nuksaan 1R se zyada ho sakta).
# usage: python pick_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, bisect, random, datetime, collections

LINES = []
COST = 0.0025


def log(s=''):
    print(s, flush=True); LINES.append(s)


def rsi(c, n=14):
    out = [None] * len(c); g = l = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]; gi, li = max(d, 0), max(-d, 0)
        if i <= n:
            g += gi / n; l += li / n
            if i == n: out[i] = 100 - 100 / (1 + g / l) if l else 100
        else:
            g = (g * (n - 1) + gi) / n; l = (l * (n - 1) + li) / n; out[i] = 100 - 100 / (1 + g / l) if l else 100
    return out


def ema(v, n):
    a = 2.0 / (n + 1); e = None; o = []
    for x in v:
        e = x if e is None else a * x + (1 - a) * e; o.append(e)
    return o


# regime_study.struct_sig ki copy (regime_study import karne par uska poora run chal padta hai)
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


def walk(o, h, l, c, j, n, en, stop, hold, tp, mode):
    """mode INTRA: din me low <= stop -> stop (gap me open). CLOSE: close < stop -> us din close par bahar."""
    end = min(j + hold, n)
    for k in range(j, end):
        if mode == 'INTRA':
            if l[k] <= stop: return stop if k == j else min(o[k], stop)
        if tp is not None and h[k] >= tp: return tp if k == j else max(o[k], tp)
        if mode == 'CLOSE' and c[k] < stop: return c[k]
    return c[end - 1]


def main():
    bhav, out_dir = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'out')
    os.makedirs(out_dir, exist_ok=True)
    data = collections.defaultdict(dict)
    for fn in glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')):
        with open(fn, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[1].strip() != 'EQ': continue
                try:
                    d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
                    t = (float(r[4]), float(r[5]), float(r[6]), float(r[8]), float(r[10]), float(r[11]) / 100.0)
                except ValueError:
                    continue
                if t[3] > 0: data[r[0].strip()][d] = t
    alld = sorted({d for v in data.values() for d in v})
    ab, tot = collections.Counter(), collections.Counter(); a50 = 2.0 / 51
    for byd in data.values():
        ds = sorted(byd); e = None
        for k, d in enumerate(ds):
            c = byd[d][3]; e = c if e is None else a50 * c + (1 - a50) * e
            if k >= 60 and byd[d][5] >= 1: tot[d] += 1; ab[d] += c > e
    reg = {d: ('STRONG' if 100.0 * ab[d] / tot[d] >= 60 else 'MIXED' if 100.0 * ab[d] / tot[d] >= 40 else 'WEAK' if 100.0 * ab[d] / tot[d] >= 25 else 'VWEAK')
           for d in alld if tot[d] >= 50}
    log('STOP-LOSS + ROZ KE 2 PICK STUDY (%s): %s se %s, %d stocks' % (datetime.date.today(), alld[0], alld[-1], len(data)))
    STOPS = [('INTRA 2ATR (abhi)', 'INTRA', 2.0), ('CLOSE 2ATR', 'CLOSE', 2.0), ('INTRA 3ATR', 'INTRA', 3.0), ('CLOSE 1.5ATR', 'CLOSE', 1.5)]
    T = []          # dict per signal
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 80: continue
        n = len(ds); b = [byd[x] for x in ds]
        o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]; to = [x[5] for x in b]
        rs = rsi(c); e20 = ema(c, 20); e50 = ema(c, 50)
        PH = [p for p in range(2, n - 2) if h[p] > max(h[p - 2:p]) and h[p] >= max(h[p + 1:p + 3])]
        PL = [p for p in range(2, n - 2) if l[p] < min(l[p - 2:p]) and l[p] <= min(l[p + 1:p + 3])]
        fired = set(); busy = collections.Counter()
        for i in range(60, n - 1):
            rg = reg.get(ds[i])
            if rg not in ('VWEAK', 'WEAK'): continue
            turn = sum(to[i - 20:i]) / 20.0
            if turn < 5 or c[i] > 6000 or any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 21, i)): continue
            ret3, ret10 = c[i] / c[i - 3] - 1, c[i] / c[i - 10] - 1
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]; atr = sum(tr) / 14.0
            sigs = []
            st = struct_sig(h, l, c, i, PH, PL, fired)
            if rg == 'VWEAK':
                if c[i] < e50[i] and rs[i] is not None and rs[i] < 30 and ret3 <= -0.08: sigs.append(('OVERSOLD_BOUNCE', 5, None, None))
                if rs[i] is not None and rs[i] < 25 and ret10 <= -0.15: sigs.append(('DEEP_OVERSOLD', 5, None, None))
                if c[i] <= c[i - 1] * 0.90: sigs.append(('DROP10', 3, 'mean', None))
                if st: sigs.append((st[0], 10, '2R', st[1] * 0.998))
            if rg == 'WEAK':
                up = c[i] > e50[i] and e20[i] > e50[i] and e50[i] > e50[i - 10]
                if up and ret3 <= -0.08: sigs.append(('DIP_A', 5, None, None))
            if not sigs: continue
            j = i + 1
            if o[j] > c[i] * 1.015 or o[j] < c[i] * 0.97: continue
            en = o[j]
            for name, hold, tgt, swing in sigs:
                if i <= busy[name]: continue
                busy[name] = j + 2
                res = {}
                for lab, mode, mult in STOPS:
                    stop = swing if swing else en - mult * atr
                    if swing and mult != 2.0: stop = en - (en - swing) * mult / 2.0   # struct: swing SL ko usi anupaat me
                    risk = en - stop
                    if risk <= en * 0.005 or risk > en * 0.25: res = None; break
                    tp = (en + 2 * risk) if tgt == '2R' else ((sum(c[i - 19:i + 1]) / 20.0) if tgt == 'mean' else None)
                    if tp is not None and tp <= en: tp = None
                    ex = walk(o, h, l, c, j, n, en, stop, hold, tp, mode)
                    res[lab] = (ex - en) / risk - COST * en / risk
                if res is None: continue
                T.append(dict(setup=name, d=ds[i], rg=rg, sym=sym, rsi=rs[i] or 50, turn=turn, atrp=atr / c[i], ret3=ret3, res=res))
    labs = [s[0] for s in STOPS]
    log('Kul signal: %d. R = Rs500 risk par kitne guna. "saal+" = (20+ trade) plus saal. "bura hafta" = hafte ka avg <= -0.7R.' % len(T))

    def stats(rows, lab):
        if not rows: return None
        v = [x['res'][lab] for x in rows]
        yrs = collections.defaultdict(list); wk = collections.defaultdict(list)
        for x in rows: yrs[x['d'].year].append(x['res'][lab]); wk[x['d'].isocalendar()[:2]].append(x['res'][lab])
        yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
        bad = sum(1 for w in wk.values() if sum(w) / len(w) <= -0.7)
        worst = min(v)
        return '%6d %4.0f%% %+6.2fR  %d/%d  bura hafta %d/%d  sabse bura %+.1fR' % (
            len(v), 100.0 * sum(1 for x in v if x > 0) / len(v), sum(v) / len(v), yp, yt, bad, len(wk), worst)
    # 1) stop-loss
    log(''); log('===== 1) STOP-LOSS: din ke beech vs close par =====')
    for sname in ('OVERSOLD_BOUNCE', 'DEEP_OVERSOLD', 'DROP10', 'STRUCT', 'STRUCT_DEEP', 'DIP_A', 'SAB'):
        rows = [x for x in T if sname == 'SAB' or x['setup'] == sname]
        if not rows: continue
        log(''); log('-- %s --' % sname)
        log('%-20s %6s %5s %7s' % ('stop', 'n', 'jeet', 'avg R'))
        for lab in labs:
            s_ = stats(rows, lab)
            if s_: log('%-20s %s' % (lab, s_))
    # 2) roz ke 2
    byday = collections.defaultdict(list)
    for x in T: byday[x['d']].append(x)
    PRI = {'STRUCT': 0, 'STRUCT_DEEP': 1, 'DROP10': 2, 'OVERSOLD_BOUNCE': 3, 'DIP_A': 4, 'DEEP_OVERSOLD': 5}
    RANK = [('SAB (har signal)', None),
            ('Liquidity sabse zyada', lambda z: -z['turn']),
            ('ATR% sabse kam (shant stock)', lambda z: z['atrp']),
            ('ATR% sabse zyada', lambda z: -z['atrp']),
            ('Setup priority (STRUCT>DROP10>BOUNCE>A>DEEP)', lambda z: (PRI.get(z['setup'], 9), -z['turn'])),
            ('3 din me sabse zyada gira', lambda z: z['ret3']),
            ('3 din me sabse kam gira', lambda z: -z['ret3']),
            ('RSI sabse kam', lambda z: z['rsi'])]
    for lab in (labs[0], labs[1]):
        log(''); log('===== 2) ROZ KE 2 (max 2 naye trade/din, ek stock ek baar) | stop: %s =====' % lab)
        log('%-46s %6s %5s %7s' % ('kaise chuna', 'n', 'jeet', 'avg R'))
        for name, key in RANK:
            if key is None:
                rows = T
            else:
                rows = []
                for d, L in byday.items():
                    seen, pick = set(), []
                    for z in sorted(L, key=key):
                        if z['sym'] in seen: continue
                        seen.add(z['sym']); pick.append(z)
                        if len(pick) == 2: break
                    rows += pick
            log('%-46s %s' % (name, stats(rows, lab)))
        rnd = random.Random(1); avgs = []
        for _ in range(50):
            rows = []
            for d, L in byday.items():
                u = {}
                for z in L: u.setdefault(z['sym'], z)
                rows += rnd.sample(list(u.values()), min(2, len(u)))
            avgs.append(sum(x['res'][lab] for x in rows) / len(rows))
        avgs.sort()
        log('%-46s avg %+.2fR (50 baar: %+.2f se %+.2f)' % ('Random 2 (tulna)', sum(avgs) / len(avgs), avgs[2], avgs[-3]))
    open(os.path.join(out_dir, 'pick_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
