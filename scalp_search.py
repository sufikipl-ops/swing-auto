# User: "scalping ka koi niyam dhoondo". Systematic search, intraday (15-min, F&O ~214 stock, ~1 saal, data_orb/).
# Imaandari ke liye: pehle aadhe saal (DISCOVERY) me niyam chuno, doosre aadhe (TEST, jo dekha nahi) me jaancho. Kharcha 0.10%.
# Families:
#  A) Opening drive: 9:15-9:30 / 9:15-10:15 ka move -> wahi disha (cont) ya ulti (rev), exit 15:15
#  B) Gap: gap size bucket -> 9:30 entry, exit 15:15 ya kal ke close (gap fill) par
#  C) Intraday momentum (academic: din ka pehla hissa aakhri ghante ko predict karta hai): 9:15-14:15 move -> 14:15 entry, 15:15 exit
#  D) Cross-section (relative strength): 10:15 tak sabse tez / sabse kamzor top5 -> long/short till 15:15
#  E) VWAP stretch: 12:00 par VWAP se 2%+ door -> mean reversion till 15:15
#  F) Prev day: kal high ke paas band (close in top 10%) -> aaj 9:30 long; kal low ke paas -> short
# usage: python scalp_search.py <data_orb_dir> <out_dir>
import os, sys, json, collections, statistics

COST = 0.10
LINES = []


def log(s=''):
    print(s, flush=True); LINES.append(s)


def load(d):
    out = {}
    for fn in os.listdir(d):
        by = collections.defaultdict(list)
        for c in json.load(open(os.path.join(d, fn))):
            t = str(c[0]); day, hm = t[:10], t[11:16]
            if '09:15' <= hm <= '15:15' and None not in c[1:5]:
                by[day].append((hm, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5] or 0)))
        out[fn[:-5]] = {k: sorted(v) for k, v in by.items() if len(v) >= 24}
    return out


def at(cs, hm):
    for x in cs:
        if x[0] >= hm: return x
    return cs[-1]


def main():
    D = load(sys.argv[1]); out_dir = sys.argv[2] if len(sys.argv) > 2 else 'out'
    days = sorted({d for v in D.values() for d in v}); mid = days[len(days) // 2]
    log('SCALP SEARCH: %d stock, %d din (%s .. %s), discovery < %s <= test, kharcha %.2f%%' % (len(D), len(days), days[0], days[-1], mid, COST))
    R = collections.defaultdict(list)          # rule -> [(day, pct)]
    xs = collections.defaultdict(list)         # day -> [(sym, ret10_15, cs, pc)]
    def add(rule, d, en, ex, side):
        if en > 0: R[rule].append((d, ((ex / en - 1) if side > 0 else (en / ex - 1)) * 100 - COST))
    for sym, by in D.items():
        dl = sorted(by)
        for i in range(1, len(dl)):
            d = dl[i]; cs = by[d]; pcs = by[dl[i - 1]]; pc = pcs[-1][4]; O = cs[0][1]; C = cs[-1][4]
            p930, p1015, p1415, p12 = cs[0][4], at(cs, '10:15')[4], at(cs, '14:15')[4], at(cs, '12:00')[4]
            g = (O / pc - 1) * 100; m15 = (p930 / O - 1) * 100; m60 = (p1015 / O - 1) * 100; m1415 = (p1415 / O - 1) * 100
            # A
            for nm, mv, en, ent in (('15m', m15, p930, '9:30'), ('60m', m60, p1015, '10:15')):
                for th in (0.5, 1.0, 2.0):
                    if mv >= th:
                        add('A %s +%.1f%% -> long (cont) %s-15:15' % (nm, th, ent), d, en, C, 1); add('A %s +%.1f%% -> short (rev)' % (nm, th), d, en, C, -1)
                    if mv <= -th:
                        add('A %s -%.1f%% -> short (cont)' % (nm, th), d, en, C, -1); add('A %s -%.1f%% -> long (rev)' % (nm, th), d, en, C, 1)
            # B
            for lo, hi in ((1, 2), (2, 4), (4, 99)):
                if lo <= g < hi:
                    add('B gap-up %d-%d%% -> short 9:30, 15:15' % (lo, hi), d, p930, C, -1); add('B gap-up %d-%d%% -> long 9:30, 15:15' % (lo, hi), d, p930, C, 1)
                if -hi < g <= -lo:
                    add('B gap-down %d-%d%% -> long 9:30, 15:15' % (lo, hi), d, p930, C, 1); add('B gap-down %d-%d%% -> short 9:30, 15:15' % (lo, hi), d, p930, C, -1)
                    # gap fill target = kal ka close
                    ex = None
                    for x in cs[1:]:
                        if x[2] >= pc: ex = pc; break
                    add('B gap-down %d-%d%% -> long 9:30, target gap-fill/15:15' % (lo, hi), d, p930, ex or C, 1)
            # C
            for th in (0.5, 1.5, 3.0):
                if m1415 >= th: add('C din +%.1f%% tak 14:15 -> long 14:15-15:15' % th, d, p1415, C, 1)
                if m1415 <= -th: add('C din -%.1f%% tak 14:15 -> short 14:15-15:15' % th, d, p1415, C, -1)
            # E
            seg = [x for x in cs if x[0] <= '12:00']; vv = sum(x[5] for x in seg)
            if vv:
                vw = sum((x[2] + x[3] + x[4]) / 3 * x[5] for x in seg) / vv; st = (p12 / vw - 1) * 100
                if st <= -2: add('E 12:00 VWAP se 2%+ neeche -> long till 15:15', d, p12, C, 1)
                if st >= 2: add('E 12:00 VWAP se 2%+ upar -> short till 15:15', d, p12, C, -1)
            # F
            ph, pl = max(x[2] for x in pcs), min(x[3] for x in pcs)
            if ph > pl:
                pos = (pc - pl) / (ph - pl)
                if pos >= 0.9: add('F kal high ke paas band -> long 9:30-15:15', d, p930, C, 1); add('F kal high ke paas band -> short 9:30-15:15', d, p930, C, -1)
                if pos <= 0.1: add('F kal low ke paas band -> long 9:30-15:15', d, p930, C, 1); add('F kal low ke paas band -> short 9:30-15:15', d, p930, C, -1)
            xs[d].append((sym, m60, p1015, C))
    # D cross-section
    for d, L in xs.items():
        if len(L) < 50: continue
        L.sort(key=lambda x: x[1])
        for s, m, en, C in L[-5:]:
            add('D 10:15 tak TOP5 tez -> long', d, en, C, 1); add('D 10:15 tak TOP5 tez -> short (rev)', d, en, C, -1)
        for s, m, en, C in L[:5]:
            add('D 10:15 tak BOTTOM5 -> long (rev)', d, en, C, 1); add('D 10:15 tak BOTTOM5 -> short', d, en, C, -1)
    rows = []
    for k, v in R.items():
        a = [p for d, p in v if d < mid]; b = [p for d, p in v if d >= mid]
        if len(a) < 40 or len(b) < 40: continue
        mo = collections.defaultdict(list)
        for d, p in v: mo[d[:7]].append(p)
        mp = sum(1 for z in mo.values() if sum(z) > 0)
        rows.append((statistics.mean(a), statistics.mean(b), k, len(a), len(b), 100 * sum(1 for p in b if p > 0) / len(b), mp, len(mo)))
    rows.sort(reverse=True)
    log('Sort: DISCOVERY avg. Pass = dono hisse plus aur TEST avg >= +0.10%.')
    log('%-58s %7s %7s %6s %6s %5s %s' % ('niyam', 'disc%', 'TEST%', 'n_d', 'n_t', 'jeet', 'mahine+'))
    for a, b, k, na, nb, w, mp, mt in rows:
        log('%-58s %+6.2f %+6.2f %6d %6d %4.0f%% %d/%d %s' % (k, a, b, na, nb, w, mp, mt, ' <== PASS' if a > 0 and b >= 0.10 else ''))
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, 'scalp_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
