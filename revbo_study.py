# LTTS sawaal: "neeche ke trend se nikalta breakout". LTTS 14-Oct-2026: 20-din high toota, volume 3x, +5.4%, par EMA20 < EMA50 tha,
# isliye hamare screen (BREAKOUT me EMA20 > EMA50 zaroori) ne nahi pakda. Kya aise "reversal breakout" me fayda hai?
# Setups (aaj close par, kal OPEN par entry, gap +1.5%/-3% skip, kharcha 0.25%, SL 2 ATR, 5/10/20 din):
#   BO_UP   : abhi ka niyam: close > pichhle 20 din ka high, volume >= 1.5x, close > EMA50, EMA20 > EMA50, din plus
#   BO_REV  : wahi par EMA20 <= EMA50 (trend palat raha)
#   BO_REV_STRONG : BO_REV + din >= 4% + volume >= 3x (LTTS jaisa)
#   BASE    : random liquid din
# usage: python revbo_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, random, datetime, collections

LINES = []


def log(s=''):
    print(s, flush=True); LINES.append(s)


def ema(v, n):
    a = 2.0 / (n + 1); e = None; o = []
    for x in v:
        e = x if e is None else a * x + (1 - a) * e; o.append(e)
    return o


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
    log('REVERSAL BREAKOUT STUDY (%s): %s se %s, %d stocks' % (datetime.date.today(), alld[0], alld[-1], len(data)))
    R = collections.defaultdict(list); rnd = random.Random(7); HOLDS = (5, 10, 20)
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 80: continue
        b = [byd[d] for d in ds]; o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]
        v = [x[4] for x in b]; to = [x[5] for x in b]
        e20, e50 = ema(c, 20), ema(c, 50)
        busy = collections.Counter()
        for i in range(55, len(c) - 1):
            if sum(to[i - 20:i]) / 20.0 < 5 or c[i] > 6000 or any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 21, i + 1)):
                continue
            prevhi = max(h[i - 20:i]); vx = v[i] / (sum(v[i - 20:i]) / 20.0); chg = (c[i] / c[i - 1] - 1) * 100
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]; atr = sum(tr) / 14.0
            bo = c[i] > prevhi and vx >= 1.5 and c[i] > e50[i] and chg > 0
            tags = []
            if bo and e20[i] > e50[i]: tags.append('BO_UP (abhi ka niyam)')
            if bo and e20[i] <= e50[i]:
                tags.append('BO_REV (EMA20<=EMA50)')
                if chg >= 4 and vx >= 3: tags.append('BO_REV_STRONG (+4%, vol 3x)')
            if rnd.random() < 0.01: tags.append('BASE: random din')
            if not tags: continue
            j = i + 1
            if o[j] > c[i] * 1.015 or o[j] < c[i] * 0.97: continue
            en = o[j]; stop = en - 2 * atr
            late = (c[i] - prevhi) / atr > 1.0
            for tg in tags:
                if i <= busy[tg]: continue
                last_k = j
                for hold in HOLDS:
                    ex = None
                    for k in range(j, min(len(c), j + hold)):
                        if l[k] <= stop: ex = (min(o[k], stop) if k > j else stop, k); break
                    if ex is None: k = min(len(c), j + hold) - 1; ex = (c[k], k)
                    pc = (ex[0] / en - 1) * 100 - 0.25; last_k = max(last_k, ex[1])
                    for rk in (reg.get(ds[i], '?'), 'ALL'):
                        R[(tg, hold, rk)].append((ds[i].year, pc))
                        if not tg.startswith('BASE'):
                            R[(tg + (' LATE(>1ATR)' if late else ' fresh'), hold, rk)].append((ds[i].year, pc))
                busy[tg] = j + 4                       # ek stock me 5 din me ek hi signal
    tags = ['BASE: random din', 'BO_UP (abhi ka niyam)', 'BO_UP (abhi ka niyam) fresh', 'BO_UP (abhi ka niyam) LATE(>1ATR)',
            'BO_REV (EMA20<=EMA50)', 'BO_REV (EMA20<=EMA50) fresh', 'BO_REV (EMA20<=EMA50) LATE(>1ATR)',
            'BO_REV_STRONG (+4%, vol 3x)', 'BO_REV_STRONG (+4%, vol 3x) fresh', 'BO_REV_STRONG (+4%, vol 3x) LATE(>1ATR)']
    log('avg% = kharcha kaat ke (0.25%), SL 2 ATR, kal open par entry. "saal+" = kitne saal (20+ trade) avg plus.')
    for hold in HOLDS:
        log(''); log('===== %d din rakho =====' % hold)
        log('%-44s %-7s %6s %5s %8s  %s' % ('setup', 'market', 'n', 'jeet', 'avg%', 'saal+'))
        for tg in tags:
            for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
                vv = R.get((tg, hold, rk))
                if not vv or (rk != 'ALL' and len(vv) < 30): continue
                yrs = collections.defaultdict(list)
                for y, p in vv: yrs[y].append(p)
                yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
                log('%-44s %-7s %6d %4.0f%% %+7.2f%%  %d/%d' % (tg, rk, len(vv), 100.0 * sum(1 for x in vv if x[1] > 0) / len(vv), sum(x[1] for x in vv) / len(vv), yp, yt))
    open(os.path.join(out_dir, 'revbo_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
