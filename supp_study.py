# "ACE jaisa" setup (27 Oct 2026): achha stock (lambi uptrend, EMA200 upar ja raha) market ke saath 60-din high se 15%+ gira aur
# pichhle 6 mahine ke PURANE SAHARA (support) par aaya, jahan se pehle 2+ baar uchhla tha (ACE: 979 ke paas, June-July ke low
# 958-979). Wahan se uchhal pakadna.
# Support = swing lows (3 din dono taraf) din i-150..i-15 me; zone = aaj ke low ke 3% neeche se 2% upar tak jitne swing low.
# Signals:
#   TOUCH   : aaj low zone me aaya aur close zone ke neeche nahi (sahara tika) -> kal open entry
#   CONFIRM : TOUCH ke baad 5 din me close > pichhle din ka high (palti pakki, ACE 27 Oct) -> kal open entry
#   + RSI<35 / 2+ touch vs 3+ touch / uptrend wala vs bina uptrend
# SL = zone ka sabse neecha low - 0.5 ATR (close par aur din ke beech dono), exit 2R ya 10 din; aur sirf 5 din.
# Kharcha 0.25%. Tulna: random din (SL 2 ATR). R me. Market haal + saal.
# usage: python supp_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, random, datetime, collections

LINES = []
COST = 0.0025


def log(s=''):
    print(s, flush=True); LINES.append(s)


def ema(v, n):
    a = 2.0 / (n + 1); e = None; o = []
    for x in v:
        e = x if e is None else a * x + (1 - a) * e; o.append(e)
    return o


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


def sim(o, h, l, c, j, en, stop, mode, hold, tgt):
    n = len(c); risk = en - stop; tp = en + tgt * risk if tgt else None; end = min(j + hold, n)
    for k in range(j, end):
        if mode == 'INTRA' and l[k] <= stop: return stop if k == j else min(o[k], stop)
        if tp and h[k] >= tp: return tp if k == j else max(o[k], tp)
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
            cc = byd[d][3]; e = cc if e is None else a50 * cc + (1 - a50) * e
            if k >= 60 and byd[d][5] >= 1: tot[d] += 1; ab[d] += cc > e
    reg = {d: ('STRONG' if 100.0 * ab[d] / tot[d] >= 60 else 'MIXED' if 100.0 * ab[d] / tot[d] >= 40 else 'WEAK' if 100.0 * ab[d] / tot[d] >= 25 else 'VWEAK')
           for d in alld if tot[d] >= 50}
    log('SUPPORT BOUNCE ("ACE jaisa") STUDY (%s): %s se %s, %d stocks' % (datetime.date.today(), alld[0], alld[-1], len(data)))
    R = collections.defaultdict(list); rnd = random.Random(4)
    EX = [('CLOSE', 10, 2.0, 'SL close, 2R/10d'), ('INTRA', 10, 2.0, 'SL din-beech, 2R/10d'), ('CLOSE', 5, None, 'SL close, 5 din')]
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 260: continue
        n = len(ds); b = [byd[x] for x in ds]
        o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]; to = [x[5] for x in b]
        e200 = ema(c, 200); rs = rsi(c)
        piv = [p for p in range(3, n - 3) if l[p] <= min(l[p - 3:p]) and l[p] <= min(l[p + 1:p + 4])]
        touch_at = {}            # i -> (zone_low, touches, tags) jab TOUCH hua
        busy = collections.Counter()
        for i in range(210, n - 1):
            if sum(to[i - 20:i]) / 20.0 < 5 or c[i] > 6000 or any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 21, i + 1)):
                continue
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]; atr = sum(tr) / 14.0
            sigs = []
            hi60 = max(h[i - 60:i])
            if c[i] <= 0.85 * hi60:
                zl = [l[p] for p in piv if i - 150 <= p <= i - 15 and l[i] * 0.98 <= l[p] <= l[i] * 1.03]
                if len(zl) >= 2 and c[i] >= min(zl):
                    up = e200[i] > e200[i - 120]
                    tg = ['TOUCH']
                    if up: tg.append('TOUCH +uptrend')
                    if rs[i] is not None and rs[i] < 35: tg.append('TOUCH +RSI<35')
                    if len(zl) >= 3: tg.append('TOUCH +3 touch')
                    if up and rs[i] is not None and rs[i] < 35: tg.append('TOUCH +uptrend +RSI<35')
                    touch_at[i] = (min(zl), tg)
                    sigs += [(t, min(zl)) for t in tg]
            # CONFIRM: pichhle 5 din me TOUCH, aaj close > kal ka high
            for k in range(i - 5, i):
                if k in touch_at and c[i] > h[i - 1] and l[i] >= touch_at[k][0] - 0.5 * atr:
                    zl_, tg_ = touch_at[k]
                    sigs += [(t.replace('TOUCH', 'CONFIRM'), zl_) for t in tg_]
                    break
            if rnd.random() < 0.01: sigs.append(('BASE: random din', None))
            if not sigs: continue
            j = i + 1
            if o[j] > c[i] * 1.015 or o[j] < c[i] * 0.97: continue
            en = o[j]
            for name, zlow in sigs:
                if i <= busy[name]: continue
                busy[name] = j + 4
                stop = (zlow - 0.5 * atr) if zlow else en - 2 * atr
                risk = en - stop
                if risk <= en * 0.01 or risk > en * 0.15: continue
                for mode, hold, tgt, lab in EX:
                    ex = sim(o, h, l, c, j, en, stop, mode, hold, tgt)
                    r_ = (ex - en) / risk - COST * en / risk
                    for rk in (reg.get(ds[i], '?'), 'ALL'):
                        R[(name, lab, rk)].append((ds[i].year, r_))
    names = ['BASE: random din']
    for base in ('TOUCH', 'CONFIRM'):
        names += [base, base + ' +uptrend', base + ' +RSI<35', base + ' +3 touch', base + ' +uptrend +RSI<35']
    log('R = Rs500 risk ka guna (kharcha kaat ke). "saal+" = (20+ trade) plus saal.')
    for _, _, _, lab in EX:
        log(''); log('===== %s =====' % lab)
        log('%-28s %-7s %6s %5s %7s  %s' % ('setup', 'market', 'n', 'jeet', 'avg R', 'saal+'))
        for nm in names:
            for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
                vv = R.get((nm, lab, rk))
                if not vv or (rk != 'ALL' and len(vv) < 30): continue
                yrs = collections.defaultdict(list)
                for y, p in vv: yrs[y].append(p)
                yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
                log('%-28s %-7s %6d %4.0f%% %+6.2fR  %d/%d' % (nm, rk, len(vv), 100.0 * sum(1 for x in vv if x[1] > 0) / len(vv), sum(x[1] for x in vv) / len(vv), yp, yt))
    open(os.path.join(out_dir, 'supp_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
