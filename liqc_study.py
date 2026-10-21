# Reel "Liquidity + candlestick": pichhle low (jahan sabke SL pade hote hain = liquidity) par bhav aaye to us din ka candle dekho.
# Level tootne ke baad wapas upar band (liquidity fail / sweep + rejection) -> upar; neeche hi band (liquidity chali) -> neeche.
# Reel me 5-min/1H candle, hamare paas daily data hai -> swing (daily) version:
#   L = din i-20..i-3 ka sabse neecha low (EQ_LOW: is window me 2+ din L ke 0.3 ATR ke andar = "equal lows", zyada liquidity)
#   Sweep din i: low[i] < L, aur pichhle 2 din L ke upar (pehli baar toota)
#   Candle: REJECT (close > L), HAMMER (REJECT + neeche ki pooch >= 2x body, close upar ke 1/3 me), BULL (REJECT + green + close upar
#           ke 25% me), RAN (close < L, liquidity chali), RAN_STRONG (RAN + red + close neeche ke 25% me)
# Entry kal OPEN (gap +1.5%/-3% skip), SL = sweep din ka low - 0.1 ATR (kam se kam 0.5 ATR door, 3 ATR se zyada = skip),
# exit: 2R target ya 10 din (aur sirf 5 din time exit). Kharcha 0.25%. Tulna: random din (wahi SL tareeka).
# usage: python liqc_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, random, datetime, collections

LINES = []


def log(s=''):
    print(s, flush=True); LINES.append(s)


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
    log('LIQUIDITY + CANDLESTICK (reel) STUDY (%s): %s se %s, %d stocks' % (datetime.date.today(), alld[0], alld[-1], len(data)))
    R = collections.defaultdict(list); rnd = random.Random(9)
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 60: continue
        b = [byd[d] for d in ds]; o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]
        to = [x[5] for x in b]; busy = collections.Counter()
        for i in range(25, len(c) - 1):
            if sum(to[i - 20:i]) / 20.0 < 5 or c[i] > 6000 or any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 21, i + 1)):
                continue
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]; atr = sum(tr) / 14.0
            L = min(l[i - 20:i - 2]); tags = []
            if l[i] < L and l[i - 1] >= L and l[i - 2] >= L:
                eq = sum(1 for k in range(i - 20, i - 2) if l[k] - L <= 0.3 * atr) >= 2
                rng = h[i] - l[i] or 1e-9; body = abs(c[i] - o[i]); low_wick = min(o[i], c[i]) - l[i]
                if c[i] > L:
                    tags.append('REJECT (toota, wapas upar band)')
                    if low_wick >= 2 * body and (c[i] - l[i]) / rng >= 2 / 3.0: tags.append('HAMMER (lambi neeche pooch)')
                    if c[i] > o[i] and (c[i] - l[i]) / rng >= 0.75: tags.append('BULL (green, upar band)')
                else:
                    tags.append('RAN (neeche hi band)')
                    if c[i] < o[i] and (c[i] - l[i]) / rng <= 0.25: tags.append('RAN_STRONG (red, neeche band)')
                if eq: tags += [t + ' +EQ_LOW' for t in tags]
            if rnd.random() < 0.01: tags.append('BASE: random din')
            if not tags: continue
            j = i + 1
            if o[j] > c[i] * 1.015 or o[j] < c[i] * 0.97: continue
            en = o[j]; stop = min(l[i] - 0.1 * atr, en - 0.5 * atr); risk = en - stop
            if risk <= 0 or risk > 3 * atr: continue
            for tg in tags:
                if i <= busy[tg]: continue
                busy[tg] = j + 4
                for mode in ('2R ya 10 din', '5 din'):
                    tp = en + 2 * risk if mode == '2R ya 10 din' else None; hold = 10 if tp else 5; ex = None
                    for k in range(j, min(len(c), j + hold)):
                        if l[k] <= stop: ex = stop if k == j else min(o[k], stop); break
                        if tp and h[k] >= tp: ex = tp if k == j else max(o[k], tp); break
                    if ex is None: ex = c[min(len(c), j + hold) - 1]
                    rr = (ex - en) / risk - 0.0025 * en / risk
                    for rk in (reg.get(ds[i], '?'), 'ALL'):
                        R[(tg, mode, rk)].append((ds[i].year, rr))
    tags = ['BASE: random din']
    for t in ('REJECT (toota, wapas upar band)', 'HAMMER (lambi neeche pooch)', 'BULL (green, upar band)', 'RAN (neeche hi band)', 'RAN_STRONG (red, neeche band)'):
        tags += [t, t + ' +EQ_LOW']
    log('R = risk ke hisaab se (1R = entry se SL). Kharcha kaat ke. "saal+" = kitne saal (20+ trade) avg plus.')
    for mode in ('2R ya 10 din', '5 din'):
        log(''); log('===== exit: %s =====' % mode)
        log('%-44s %-7s %6s %5s %7s  %s' % ('candle', 'market', 'n', 'jeet', 'avg R', 'saal+'))
        for tg in tags:
            for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
                vv = R.get((tg, mode, rk))
                if not vv or (rk != 'ALL' and len(vv) < 30): continue
                yrs = collections.defaultdict(list)
                for y, p in vv: yrs[y].append(p)
                yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
                log('%-44s %-7s %6d %4.0f%% %+6.2fR  %d/%d' % (tg, rk, len(vv), 100.0 * sum(1 for x in vv if x[1] > 0) / len(vv), sum(x[1] for x in vv) / len(vv), yp, yt))
    open(os.path.join(out_dir, 'liqc_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
