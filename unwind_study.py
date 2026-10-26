# oibu_study ka lead pakka karna: LONG_UNWIND (bhav gira + futures OI ghata = kharidne wale thak ke nikle) ko KHARIDNA.
# Robustness: bhav <= -2/-3/-5%, OI <= -3/-5/-10% ka poora grid; 5 aur 10 din; market haal, saal, pehla/doosra aadha.
# Overlap: kya ye sirf hamara oversold bounce hai? -> 10-din return <= -8% (oversold) wale aur baaki alag.
# Expiry: mahine ke aakhri hafte (din >= 22) OI rollover se girta hai -> alag dikhaya.
# Entry kal OPEN (gap +1.5%/-3% skip), SL 2 ATR, kharcha 0.25%. Tulna: random F&O din. OI cache: out/fo_oi.json (oibu_study).
# usage: python unwind_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, random, datetime, collections
from oibu_study import load_oi

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
    OI = load_oi(alld)
    mid = alld[len(alld) // 2]
    log('LONG UNWIND (gira + OI ghata -> kharido) PAKKA TEST (%s): %s se %s, F&O OI %d din' % (
        datetime.date.today(), alld[0], alld[-1], sum(1 for d in alld if OI.get(d.isoformat()))))
    GRID = [(p, q) for p in (-2, -3, -5) for q in (-3, -5, -10)]
    R = collections.defaultdict(list); rnd = random.Random(21); HOLDS = (5, 10)
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 40: continue
        b = [byd[d] for d in ds]; o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]
        busy = collections.Counter()
        for i in range(25, len(c) - 1):
            o_ = OI.get(ds[i].isoformat(), {}).get(sym)
            if not o_ or o_[1] <= 0: continue
            if any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 21, i + 1)): continue
            chg = (c[i] / c[i - 1] - 1) * 100; oic = (o_[0] / o_[1] - 1) * 100
            tags = ['P%d OI%d' % (p, q) for p, q in GRID if chg <= p and oic <= q]
            if 'P-2 OI-5' in tags:
                ret10 = (c[i] / c[i - 10] - 1) * 100
                tags.append('P-2 OI-5 | oversold (10d <= -8%)' if ret10 <= -8 else 'P-2 OI-5 | oversold NAHI')
                tags.append('P-2 OI-5 | expiry hafta (din>=22)' if ds[i].day >= 22 else 'P-2 OI-5 | baaki din')
                tags.append('P-2 OI-5 | ' + ('1st half' if ds[i] < mid else '2nd half'))
            if chg <= -2: tags.append('P-2 (OI dekhe bina)')
            if rnd.random() < 0.02: tags.append('BASE: random F&O din')
            if not tags: continue
            j = i + 1
            if o[j] > c[i] * 1.015 or o[j] < c[i] * 0.97: continue
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]; atr = sum(tr) / 14.0
            en = o[j]; stop = en - 2 * atr
            for hold in HOLDS:
                ex = None
                for k in range(j, min(len(c), j + hold)):
                    if l[k] <= stop: ex = stop if k == j else min(o[k], stop); break
                if ex is None: ex = c[min(len(c), j + hold) - 1]
                pc = (ex / en - 1) * 100 - 0.25
                for tg in tags:
                    if i <= busy[(tg, hold)]: continue
                    busy[(tg, hold)] = j + 2                  # ek stock me 3 din me ek hi signal
                    for rk in (reg.get(ds[i], '?'), 'ALL'):
                        R[(tg, hold, rk)].append((ds[i].year, pc))
    tags = ['BASE: random F&O din', 'P-2 (OI dekhe bina)'] + ['P%d OI%d' % g for g in GRID] + [
        'P-2 OI-5 | oversold (10d <= -8%)', 'P-2 OI-5 | oversold NAHI', 'P-2 OI-5 | expiry hafta (din>=22)', 'P-2 OI-5 | baaki din',
        'P-2 OI-5 | 1st half', 'P-2 OI-5 | 2nd half']
    log('avg% = kharcha (0.25%) kaat ke, SL 2 ATR, kal open par entry. P = bhav badlav %, OI = OI badlav %. "saal+" = (20+ trade wale) plus saal.')
    for hold in HOLDS:
        log(''); log('===== %d din rakho =====' % hold)
        log('%-36s %-7s %6s %5s %8s  %s' % ('setup', 'market', 'n', 'jeet', 'avg%', 'saal+'))
        for tg in tags:
            for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
                vv = R.get((tg, hold, rk))
                if not vv or (rk != 'ALL' and len(vv) < 30): continue
                yrs = collections.defaultdict(list)
                for y, p in vv: yrs[y].append(p)
                yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
                log('%-36s %-7s %6d %4.0f%% %+7.2f%%  %d/%d' % (tg, rk, len(vv), 100.0 * sum(1 for x in vv if x[1] > 0) / len(vv), sum(x[1] for x in vv) / len(vv), yp, yt))
    open(os.path.join(out_dir, 'unwind_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
