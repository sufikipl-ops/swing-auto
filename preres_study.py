# User ka sawaal: "result aane se pehle andaza laga sakte hain kya?" Sirf result se PEHLE ki jaankari se test:
#   PREV_GOOD/BAD : pichhle result (50-130 din pehle) ke reaction din par stock +3% / -3%  (earnings momentum)
#   RUNUP/DOWNRUN : entry se pehle 20 din me stock +10% / -10%
#   DELIV_UP      : pichhle 5 din ka delivery% > 20-din avg x1.2 (log pehle se jama kar rahe?)
#   SEASON_GOOD/BAD: pichhle 10 din me jin liquid companies ka result aaya, unka avg reaction > +0.5% / < -0.5%
#   SCORE2+       : upar ke achhe signals (PREV_GOOD, SEASON_GOOD, DELIV_UP, not RUNUP) me se 2+
# Trade: reaction din se 3 trading din pehle close par kharido, reaction ke 2 din baad close par becho (SL 2 ATR, gap par
# stop ka asli bhav). Kharcha 0.25%. Tulna: saare results (bina andaze) aur random liquid 5-din hold.
# Board meeting ki date result se ~1 hafta pehle NSE par aa jaati hai, isliye pehle se kharidna mumkin hai.
# usage: python preres_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, random, datetime, collections
from results_study import result_dates

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
                try:
                    dv = float(r[14])
                except ValueError:
                    dv = None
                if t[3] > 0: data[r[0].strip()][d] = t + (dv,)
    alld = sorted({d for v in data.values() for d in v})
    log('RESULT SE PEHLE ANDAZA (pre-result) STUDY (%s): bhav %s se %s, %d stocks' % (datetime.date.today(), alld[0], alld[-1], len(data)))
    ev = result_dates(alld[0], alld[-1])
    log('NSE results mile: %d' % len(ev))
    ab, tot = collections.Counter(), collections.Counter(); a50 = 2.0 / 51
    for byd in data.values():
        ds = sorted(byd); e = None
        for k, d in enumerate(ds):
            c = byd[d][3]; e = c if e is None else a50 * c + (1 - a50) * e
            if k >= 60 and byd[d][5] >= 1: tot[d] += 1; ab[d] += c > e
    reg = {d: ('STRONG' if 100.0 * ab[d] / tot[d] >= 60 else 'MIXED' if 100.0 * ab[d] / tot[d] >= 40 else 'WEAK' if 100.0 * ab[d] / tot[d] >= 25 else 'VWEAK')
           for d in alld if tot[d] >= 50}
    idx = {s: sorted(b) for s, b in data.items()}

    # 1) har result ka reaction din aur reaction (din ka %)
    evs = []
    for sym, t in ev:
        if sym not in data: continue
        dt = datetime.datetime.strptime(t, '%Y-%m-%d %H:%M'); ds = idx[sym]
        rd_ = dt.date() if dt.hour * 60 + dt.minute < 9 * 60 + 15 else dt.date() + datetime.timedelta(days=1)
        i = next((k for k, d in enumerate(ds) if d >= rd_), None)
        if i is None or i < 30 or i + 2 >= len(ds) or (ds[i] - rd_).days > 5: continue
        c = [data[sym][d][3] for d in ds[i - 25:i + 3]]
        if any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(1, len(c) - 3)): continue
        liq = sum(data[sym][d][5] for d in ds[i - 23:i - 3]) / 20.0 >= 5
        react = (data[sym][ds[i]][3] / data[sym][ds[i - 1]][3] - 1) * 100
        evs.append((sym, i, ds[i], react, liq))
    by_sym = collections.defaultdict(list)
    for e in evs: by_sym[e[0]].append(e)
    liq_by_day = sorted((e[2], e[3]) for e in evs if e[4])

    R = collections.defaultdict(list); RX = collections.defaultdict(list); n_ev = 0

    def add(tag, rg, yr, pc, react):
        for rk in (rg, 'ALL'):
            R[(tag, rk)].append((yr, pc)); RX[(tag, rk)].append(react)

    for sym, i, d0, react, liq in evs:
        if not liq: continue
        ds = idx[sym]; b = [data[sym][d] for d in ds]
        o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]; dv = [x[6] for x in b]
        ie = i - 3                                          # entry: reaction din se 3 din pehle close
        tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(ie - 13, ie + 1)]
        atr = sum(tr) / 14.0; en = c[ie]; stop = en - 2 * atr; ex = None
        for k in range(ie + 1, i + 3):
            if l[k] <= stop: ex = min(o[k], stop); break
        if ex is None: ex = c[i + 2]
        pc = (ex / en - 1) * 100 - 0.25
        # andaze ke signals (sab ie tak ki jaankari)
        prev = [e for e in by_sym[sym] if 50 <= (d0 - e[2]).days <= 130]
        prev_r = prev[-1][3] if prev else None
        run = (c[ie] / c[ie - 20] - 1) * 100
        dd = [x for x in dv[ie - 19:ie + 1] if x is not None]; d5 = [x for x in dv[ie - 4:ie + 1] if x is not None]
        deliv_up = len(dd) >= 15 and len(d5) >= 4 and sum(d5) / len(d5) > 1.2 * sum(dd) / len(dd)
        dE = ds[ie]
        seas = [r_ for dd_, r_ in liq_by_day if dE - datetime.timedelta(days=10) <= dd_ < dE]
        seas_avg = sum(seas) / len(seas) if len(seas) >= 10 else None
        rg = reg.get(dE, '?'); yr = dE.year; n_ev += 1
        add('ALL results (bina andaza)', rg, yr, pc, react)
        if prev_r is not None and prev_r >= 3: add('PREV_GOOD (pichhla result +3%)', rg, yr, pc, react)
        if prev_r is not None and prev_r <= -3: add('PREV_BAD (pichhla result -3%)', rg, yr, pc, react)
        if run >= 10: add('RUNUP (20 din +10%)', rg, yr, pc, react)
        if run <= -10: add('DOWNRUN (20 din -10%)', rg, yr, pc, react)
        if deliv_up: add('DELIV_UP (delivery badhi)', rg, yr, pc, react)
        if seas_avg is not None and seas_avg > 0.5: add('SEASON_GOOD (baaki results achhe)', rg, yr, pc, react)
        if seas_avg is not None and seas_avg < -0.5: add('SEASON_BAD (baaki results bure)', rg, yr, pc, react)
        sc = (prev_r is not None and prev_r >= 3) + (seas_avg is not None and seas_avg > 0.5) + deliv_up + (run < 10)
        if sc >= 3: add('SCORE3+ (achhe signals)', rg, yr, pc, react)
        if (prev_r is not None and prev_r >= 3) and (seas_avg is not None and seas_avg > 0.5):
            add('PREV_GOOD + SEASON_GOOD', rg, yr, pc, react)
    rnd = random.Random(11)
    for sym, ds in idx.items():
        for i in range(30, len(ds) - 5):
            if rnd.random() > 0.004: continue
            b = [data[sym][d] for d in ds[i - 20:i + 6]]
            if sum(x[5] for x in b[:20]) / 20.0 < 5: continue
            if any(abs(b[k][3] / b[k - 1][3] - 1) > 0.35 for k in range(1, len(b))): continue
            tr = [max(b[k][1] - b[k][2], abs(b[k][1] - b[k - 1][3]), abs(b[k][2] - b[k - 1][3])) for k in range(7, 21)]
            en = b[20][3]; stop = en - 2 * sum(tr) / 14.0; ex = None
            for k in range(21, 26):
                if b[k][2] <= stop: ex = min(b[k][0], stop); break
            if ex is None: ex = b[25][3]
            for rk in (reg.get(ds[i], '?'), 'ALL'):
                R[('BASE: random 5 din', rk)].append((ds[i].year, (ex / en - 1) * 100 - 0.25))
    log('Liquid result events: %d' % n_ev)
    log('Trade = result se 3 din pehle close par lo, result ke 2 din baad close par becho (5 din). Kharcha 0.25%, SL 2 ATR.')
    log('"result din +" = kitne % me result wale din stock plus band hua (andaza sahi?). "saal+" = kitne saal (20+ trade) avg plus.')
    tags = ['BASE: random 5 din', 'ALL results (bina andaza)', 'PREV_GOOD (pichhla result +3%)', 'PREV_BAD (pichhla result -3%)',
            'RUNUP (20 din +10%)', 'DOWNRUN (20 din -10%)', 'DELIV_UP (delivery badhi)', 'SEASON_GOOD (baaki results achhe)',
            'SEASON_BAD (baaki results bure)', 'PREV_GOOD + SEASON_GOOD', 'SCORE3+ (achhe signals)']
    log('')
    log('%-36s %-7s %6s %9s %8s %5s %8s  %s' % ('andaza', 'market', 'n', 'result din+', 'din avg', 'jeet', 'avg%', 'saal+'))
    for tg in tags:
        for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
            v = R.get((tg, rk))
            if not v or (rk != 'ALL' and len(v) < 30): continue
            x = RX.get((tg, rk)) or []
            yrs = collections.defaultdict(list)
            for y, p in v: yrs[y].append(p)
            yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
            log('%-36s %-7s %6d %9s %8s %4.0f%% %+7.2f%%  %d/%d' % (
                tg, rk, len(v), ('%.0f%%' % (100.0 * sum(1 for r_ in x if r_ > 0) / len(x))) if x else '-',
                ('%+.2f%%' % (sum(x) / len(x))) if x else '-', 100.0 * sum(1 for y in v if y[1] > 0) / len(v),
                sum(y[1] for y in v) / len(v), yp, yt))
    open(os.path.join(out_dir, 'preres_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
