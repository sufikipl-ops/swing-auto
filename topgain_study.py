# Reel (Pavan Ghuge, "bullish stocks for next 5 days"): 3:20 baje NSE par Nifty 50 kholo, % change se sort karo, sabse zyada
# chadhne wale kharido -> agle 4-5 din bullish. Test: har din "Nifty 50 jaisa" universe = pichhle 60 din ke avg turnover me top 50
# (purani Nifty list muft nahi milti). Us din % change ke hisaab se TOP1 / TOP3 / TOP5 (gainers), BOTTOM3 (losers), aur saare 50.
# Entry: (a) usi din close par (reel ka 3:20) (b) agle din open. Exit: 4 ya 5 din baad close; SL nahi (reel me nahi) aur SL 2 ATR.
# Kharcha 0.25%. Market haal (breadth) aur saal ke hisaab se.
# usage: python topgain_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, datetime, collections

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
    log('TOP GAINERS (Nifty 50 jaisa) -> AGLE 4-5 DIN STUDY (%s): %s se %s, %d stocks' % (datetime.date.today(), alld[0], alld[-1], len(data)))
    idx = {s: sorted(b) for s, b in data.items()}
    pos = {s: {d: k for k, d in enumerate(ds)} for s, ds in idx.items()}
    # har din: 60-din avg turnover (sirf pichhle din tak)
    cand = collections.defaultdict(list)            # date -> [(turn60, sym, k)]
    for s, ds in idx.items():
        if len(ds) < 80: continue
        to = [data[s][d][5] for d in ds]; run = sum(to[:60])
        for k in range(60, len(ds) - 6):
            cand[ds[k]].append((run / 60.0, s, k)); run += to[k] - to[k - 60]
    R = collections.defaultdict(list)
    for d, L in cand.items():
        top50 = sorted(L, reverse=True)[:50]
        if len(top50) < 50: continue
        rows = []
        for _, s, k in top50:
            c = [data[s][x][3] for x in idx[s][k - 15:k + 7]]
            if any(abs(c[i] / c[i - 1] - 1) > 0.35 for i in range(1, len(c))): continue
            rows.append(((data[s][idx[s][k]][3] / data[s][idx[s][k - 1]][3] - 1) * 100, s, k))
        rows.sort(reverse=True)
        groups = {'TOP1 (sabse zyada chadha)': rows[:1], 'TOP3': rows[:3], 'TOP5': rows[:5], 'BOTTOM3 (sabse zyada gira)': rows[-3:],
                  'SAB 50 (tulna)': rows, 'TOP3 jo +2% se zyada': [x for x in rows[:3] if x[0] >= 2]}
        rg = reg.get(d, '?')
        for g, sel in groups.items():
            for chg, s, k in sel:
                ds = idx[s]; b = [data[s][x] for x in ds]
                o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]
                tr = [max(h[q] - l[q], abs(h[q] - c[q - 1]), abs(l[q] - c[q - 1])) for q in range(k - 13, k + 1)]; atr = sum(tr) / 14.0
                for ent in ('close (3:20)', 'kal open'):
                    en, j0 = (c[k], k + 1) if ent.startswith('close') else (o[k + 1], k + 1)
                    for hold in (4, 5):
                        for sl in ('SL nahi', 'SL 2ATR'):
                            stop = en - 2 * atr; ex = None
                            last = (k + hold) if ent.startswith('close') else (k + hold)
                            for q in range(j0, last + 1):
                                if sl == 'SL 2ATR' and l[q] <= stop: ex = stop if (q == j0 and not ent.startswith('close')) else min(o[q], stop); break
                            if ex is None: ex = c[last]
                            pc = (ex / en - 1) * 100 - 0.25
                            for rk in (rg, 'ALL'):
                                R[(g, ent, hold, sl, rk)].append((d.year, pc))
    log('avg% = kharcha (0.25%) kaat ke. "saal+" = kitne saal (20+ trade) avg plus.')
    for ent in ('close (3:20)', 'kal open'):
        for hold in (4, 5):
            for sl in ('SL nahi', 'SL 2ATR'):
                log(''); log('===== entry %s | %d din | %s =====' % (ent, hold, sl))
                log('%-28s %-7s %6s %5s %8s  %s' % ('kaun', 'market', 'n', 'jeet', 'avg%', 'saal+'))
                for g in ('SAB 50 (tulna)', 'TOP1 (sabse zyada chadha)', 'TOP3', 'TOP5', 'TOP3 jo +2% se zyada', 'BOTTOM3 (sabse zyada gira)'):
                    for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
                        vv = R.get((g, ent, hold, sl, rk))
                        if not vv or (rk != 'ALL' and len(vv) < 30): continue
                        yrs = collections.defaultdict(list)
                        for y, p in vv: yrs[y].append(p)
                        yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
                        log('%-28s %-7s %6d %4.0f%% %+7.2f%%  %d/%d' % (g, rk, len(vv), 100.0 * sum(1 for x in vv if x[1] > 0) / len(vv), sum(x[1] for x in vv) / len(vv), yp, yt))
    open(os.path.join(out_dir, 'topgain_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
