# Reel "Moving Average Crossover" (AI & Algo Trading Part 4): 9-din average 21-din average ko neeche se upar cross kare -> buy,
# upar se neeche -> sell. Exit: stop-loss % aur target % (reel ki screen: SL -1%, target +2%). Reel ka claim: 2 saal, 84 trade, 54% jeet,
# max drawdown -14%. (Rule reel ki captions se; download me awaaz nahi thi.)
# A) NIFTY (Yahoo ^NSEI, 2008 se daily): signal close par, kal OPEN par entry/exit, kharcha 0.1% round trip. Buy & hold se tulna,
#    CAGR, max drawdown, saal-war, aur pichhle 2 saal alag (reel jaisa).
# B) Saare liquid stocks (NSE bhavcopy ~4 saal): 9/21 SMA cross up -> kal open par kharido; exit (1) SL1%/T2%, (2) cross down,
#    (3) 2ATR SL + cross down. Random din ki entry (same exit) se tulna, market haal ke hisaab se. Kharcha 0.25%.
# usage: python ma_study.py <bhav_folder> <out_folder>     (SYNTH=1 -> random walk sanity)
import os, sys, csv, glob, json, math, random, datetime, collections, urllib.request

LINES = []


def log(s=''):
    print(s, flush=True); LINES.append(s)


def sma(v, n):
    out, s = [None] * len(v), 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n: s -= v[i - n]
        if i >= n - 1: out[i] = s / n
    return out


def ema(v, n):
    a = 2.0 / (n + 1); out = []; e = None
    for x in v:
        e = x if e is None else a * x + (1 - a) * e; out.append(e)
    return out


def nifty():
    u = 'https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?period1=1199145600&period2=' + str(int(datetime.datetime.now().timestamp())) + '&interval=1d'
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read())['chart']['result'][0]
    q = d['indicators']['quote'][0]; rows = []
    for k, t in enumerate(d['timestamp']):
        o, h, l, c = q['open'][k], q['high'][k], q['low'][k], q['close'][k]
        if None in (o, h, l, c) or c <= 0:
            continue
        rows.append((datetime.date.fromtimestamp(t), o, h, l, c))
    return rows


def synth_index(n=4600, seed=1):
    r = random.Random(seed); px = 5000.0; rows = []; d = datetime.date(2008, 1, 1)
    while len(rows) < n:
        d += datetime.timedelta(1)
        if d.weekday() >= 5: continue
        o = px * math.exp(r.gauss(0, 0.004)); hi = lo = o; px = o
        for _ in range(30):
            px *= math.exp(r.gauss(0.0003 / 30, 0.011 / math.sqrt(30))); hi = max(hi, px); lo = min(lo, px)
        rows.append((d, o, hi, lo, px))
    return rows


def run_index(rows, fast, slow, kind, exit_mode, cost=0.001, short=False):
    """Signal close par, kal OPEN par amal. -> trades [(entry_date, exit_date, pct)], roz ka equity (mark-to-market)."""
    c = [r[4] for r in rows]; o = [r[1] for r in rows]; h = [r[2] for r in rows]; l = [r[3] for r in rows]
    f = (sma if kind == 'SMA' else ema)(c, fast); s = (sma if kind == 'SMA' else ema)(c, slow)
    trades, eq = [], [1.0]
    cash, side, e, ed = 1.0, 0, 0.0, None             # side 0 = koi position nahi
    want, exit_flag = 0, False                         # kal close ka signal: +1 long, -1 short, 0 kuch nahi
    for i in range(slow + 1, len(c)):
        # 1) kal ke signal par aaj OPEN par amal
        if want and want != side:
            if side:                                   # ulta signal: purani position band
                pct = (o[i] / e - 1) * side - cost; cash *= 1 + pct; trades.append((ed, rows[i][0], pct * 100)); side = 0
            if want > 0 or short:
                side, e, ed = want, o[i], rows[i][0]
        elif want == 0 and side and exit_flag:         # cross down (long only) -> bahar
            pct = (o[i] / e - 1) * side - cost; cash *= 1 + pct; trades.append((ed, rows[i][0], pct * 100)); side = 0
        # 2) SL / target (din ke andar), same din dono = SL
        if side and exit_mode == 'SLTP':
            sl = e * (1 - 0.01 * side); tp = e * (1 + 0.02 * side)
            hit_sl = l[i] <= sl if side > 0 else h[i] >= sl
            hit_tp = h[i] >= tp if side > 0 else l[i] <= tp
            if hit_sl or hit_tp:
                ex = sl if hit_sl else tp
                if ed != rows[i][0]:
                    ex = (min(o[i], sl) if side > 0 else max(o[i], sl)) if hit_sl else ((max(o[i], tp) if side > 0 else min(o[i], tp)))
                pct = (ex / e - 1) * side - cost; cash *= 1 + pct; trades.append((ed, rows[i][0], pct * 100)); side = 0
        eq.append(cash * (1 + ((c[i] / e - 1) * side if side else 0)))
        # 3) aaj close par signal
        up = f[i - 1] <= s[i - 1] and f[i] > s[i]
        dn = f[i - 1] >= s[i - 1] and f[i] < s[i]
        want = 1 if up else (-1 if dn and short else 0)
        exit_flag = dn and side > 0
    return trades, eq




def stats(trades, eq, years):
    n = len(trades); pc = [t[2] for t in trades]
    tot = eq[-1] / eq[0] - 1 if eq else 0
    peak, dd = eq[0], 0
    for x in eq:
        peak = max(peak, x); dd = min(dd, x / peak - 1)
    cagr = (eq[-1] / eq[0]) ** (1.0 / years) - 1 if years > 0 and eq[-1] > 0 else 0
    return n, (100.0 * sum(1 for x in pc if x > 0) / n if n else 0), (sum(pc) / n if n else 0), tot * 100, cagr * 100, dd * 100


def part_a(rows, tag):
    log('== A) NIFTY%s: %s se %s (%d din) ==' % (tag, rows[0][0], rows[-1][0], len(rows)))
    log('%-34s %6s %5s %8s %9s %7s %8s' % ('variant', 'trades', 'jeet', 'avg%', 'kul%', 'CAGR%', 'maxDD%'))
    yrs = (rows[-1][0] - rows[0][0]).days / 365.25
    c = [r[4] for r in rows]; bh = [x / c[0] for x in c]
    n, w, a, t, cg, dd = stats([], bh, yrs)
    log('%-34s %6s %5s %8s %+8.0f%% %+6.1f%% %+7.1f%%' % ('Buy & hold (Nifty)', '-', '-', '-', t, cg, dd))
    res = {}
    for name, fa, sl, kind, mode, sh in [('REEL: 9/21 SMA + SL1%/T2%', 9, 21, 'SMA', 'SLTP', False),
                                         ('9/21 SMA, cross down par bahar', 9, 21, 'SMA', 'CROSS', False),
                                         ('9/21 EMA, cross down par bahar', 9, 21, 'EMA', 'CROSS', False),
                                         ('9/21 SMA long+short (cross par palto)', 9, 21, 'SMA', 'CROSS', True),
                                         ('20/50 SMA, cross down par bahar', 20, 50, 'SMA', 'CROSS', False),
                                         ('50/200 SMA, cross down par bahar', 50, 200, 'SMA', 'CROSS', False)]:
        tr, eq = run_index(rows, fa, sl, kind, mode, short=sh)
        n, w, a, t, cg, dd = stats(tr, eq, yrs); res[name] = (tr, eq)
        log('%-34s %6d %4.0f%% %+7.2f%% %+8.0f%% %+6.1f%% %+7.1f%%' % (name, n, w, a, t, cg, dd))
    # pichhle 2 saal (reel jaisa) + saal-war
    cut = rows[-1][0] - datetime.timedelta(days=730)
    log(''); log('-- Pichhle 2 saal (reel ka window, %s se) --' % cut)
    k0 = next(i for i, r in enumerate(rows) if r[0] >= cut)
    sub = rows[k0:]; bh2 = [r[4] / sub[0][4] for r in sub]
    n, w, a, t, cg, dd = stats([], bh2, 2)
    log('%-34s %6s %5s %8s %+8.0f%% %+6.1f%% %+7.1f%%' % ('Buy & hold (Nifty)', '-', '-', '-', t, cg, dd))
    for name in res:
        tr = [x for x in res[name][0] if x[0] >= cut]; eq = res[name][1][-len(sub):]
        n, w, a, t, cg, dd = stats(tr, eq, 2)
        log('%-34s %6d %4.0f%% %+7.2f%% %+8.0f%% %+6.1f%% %+7.1f%%' % (name, n, w, a, (eq[-1] / eq[0] - 1) * 100, cg, dd))
    log(''); log('-- Saal-war kul return %%: REEL (SL1/T2) | 9/21 cross | Buy&hold --')
    for y in range(rows[0][0].year, rows[-1][0].year + 1):
        r1 = sum(x[2] for x in res['REEL: 9/21 SMA + SL1%/T2%'][0] if x[0].year == y)
        r2 = sum(x[2] for x in res['9/21 SMA, cross down par bahar'][0] if x[0].year == y)
        yc = [r[4] for r in rows if r[0].year == y]
        log('  %d  %+6.1f | %+6.1f | %+6.1f' % (y, r1, r2, (yc[-1] / yc[0] - 1) * 100 if yc else 0))


def part_b(bhav):
    data = collections.defaultdict(dict)
    for fn in glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')):
        with open(fn, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[1].strip() != 'EQ': continue
                try:
                    d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
                    t = (float(r[4]), float(r[5]), float(r[6]), float(r[8]), float(r[11]) / 100.0)
                except ValueError:
                    continue
                if t[3] > 0: data[r[0].strip()][d] = t
    alld = sorted({d for v in data.values() for d in v})
    ab, tot = collections.Counter(), collections.Counter(); a50 = 2.0 / 51
    for byd in data.values():
        ds = sorted(byd); e = None
        for k, d in enumerate(ds):
            cc = byd[d][3]; e = cc if e is None else a50 * cc + (1 - a50) * e
            if k >= 60 and byd[d][4] >= 1: tot[d] += 1; ab[d] += cc > e
    reg = {d: ('STRONG' if 100.0 * ab[d] / tot[d] >= 60 else 'MIXED' if 100.0 * ab[d] / tot[d] >= 40 else 'WEAK' if 100.0 * ab[d] / tot[d] >= 25 else 'VWEAK')
           for d in alld if tot[d] >= 50}
    log(''); log('== B) SAARE LIQUID STOCKS: %s se %s, %d stocks (9/21 SMA cross up -> kal open par entry, kharcha 0.25%%) ==' % (alld[0], alld[-1], len(data)))
    R = collections.defaultdict(list); rnd = random.Random(9)
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 120: continue
        b = [byd[d] for d in ds]; o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]; to = [x[4] for x in b]
        f9, s21 = sma(c, 9), sma(c, 21)
        busy = collections.Counter()
        for i in range(60, len(c) - 1):
            if sum(to[i - 19:i + 1]) / 20.0 < 5 or any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 21, i + 1)):
                continue
            cross = f9[i - 1] <= s21[i - 1] and f9[i] > s21[i]
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]; atr = sum(tr) / 14.0
            for sig in ('CROSS', 'BASE'):
                if sig == 'CROSS' and not cross: continue
                if sig == 'BASE' and (rnd.random() > 0.03 or not f9[i] > s21[i]): continue      # random din jab 9 > 21 (trend me) ho
                j = i + 1
                if o[j] > c[i] * 1.015 or o[j] < c[i] * 0.97: continue
                e = o[j]
                for ex_mode in ('SL1/T2', 'CROSSDN', '2ATR+CROSSDN'):
                    key = (sig, ex_mode)
                    if i <= busy[key]: continue
                    sl = e * 0.99 if ex_mode == 'SL1/T2' else (e - 2 * atr if ex_mode == '2ATR+CROSSDN' else None); tp = e * 1.02 if ex_mode == 'SL1/T2' else None
                    ex = None
                    for k in range(j, min(len(c), j + 60)):
                        if sl and l[k] <= sl: ex = (min(o[k], sl) if k > j else sl, k); break
                        if tp and h[k] >= tp: ex = (max(o[k], tp) if k > j else tp, k); break
                        if ex_mode != 'SL1/T2' and k - 1 > i and f9[k - 1] < s21[k - 1]:     # kal close par 9 < 21 -> aaj open par bahar
                            ex = (o[k], k); break
                    if ex is None:
                        k = min(len(c), j + 60) - 1; ex = (c[k], k)
                    busy[key] = ex[1]; pc = (ex[0] / e - 1) * 100 - 0.25
                    for rk in (reg.get(ds[i], '?'), 'ALL'):
                        R[(sig, ex_mode, rk)].append((ds[i].year, pc, ex[1] - j + 1))
    log('%-8s %-14s %-7s %7s %5s %8s %6s  %s' % ('entry', 'exit', 'market', 'n', 'jeet', 'avg%', 'din', 'saal+'))
    for ex_mode in ('SL1/T2', 'CROSSDN', '2ATR+CROSSDN'):
        for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
            for sig in ('CROSS', 'BASE'):
                v = R.get((sig, ex_mode, rk))
                if not v: continue
                yrs = collections.defaultdict(list)
                for y, p, _ in v: yrs[y].append(p)
                yp = sum(1 for y in yrs if len(yrs[y]) >= 30 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 30)
                log('%-8s %-14s %-7s %7d %4.0f%% %+7.2f%% %6.1f  %d/%d' % (sig, ex_mode, rk, len(v), 100.0 * sum(1 for x in v if x[1] > 0) / len(v),
                                                                        sum(x[1] for x in v) / len(v), sum(x[2] for x in v) / len(v), yp, yt))
        log('')


def main():
    out_dir = sys.argv[2] if len(sys.argv) > 2 else 'out'
    os.makedirs(out_dir, exist_ok=True)
    syn = bool(os.environ.get('SYNTH'))
    log('MA CROSSOVER STUDY%s (%s)' % (' [SYNTH]' if syn else '', datetime.date.today()))
    part_a(synth_index() if syn else nifty(), ' [random walk]' if syn else ' (Yahoo ^NSEI)')
    if not syn and len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        part_b(sys.argv[1])
    open(os.path.join(out_dir, 'ma_summary%s.txt' % ('_synth' if syn else '')), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
