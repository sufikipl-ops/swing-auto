# Paper trading (19-23 Oct 2026): 43 band, 2 jeete, -40R. Market VWEAK, breadth 22% -> 11% (girta hi gaya). Sawaal: VWEAK ke
# bounce setups kab kaam karte hain? Backtest ka +0.26R kahin "market palatne" wale dinon se to nahi aata?
# Setups (regime_study / dip_scan jaise): OVERSOLD_BOUNCE (EMA50 ke neeche, RSI<30, 3 din me 8%+ gira), DEEP_OVERSOLD (RSI<25,
# 10 din me 15%+ gira), DROP10 (ek din me 10%+ gira). Entry kal OPEN (gap +1.5%/-3% skip), SL 2 ATR, 5 din (DROP10: 3 din ya
# 20-din average). R me, kharcha 0.25%.
# Market haal (signal din, liquid stocks ka % EMA50 ke upar = breadth):
#   GIRTA: breadth pichhle 3 din se kam | PALAT: breadth kal se 2+ point upar | level <15 / 15-25
# Aur: ek din ke saare signal ek hi daav hain -> "din ka avg R" aur hafte-war bura daur kitni baar aaya. Top-2 (sabse kam RSI) vs sab.
# usage: python turn_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, datetime, collections

LINES = []


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
    br = {d: 100.0 * ab[d] / tot[d] for d in alld if tot[d] >= 50}
    bd = [d for d in alld if d in br]
    state = {}
    for k, d in enumerate(bd):
        b = br[d]
        if b >= 25: continue
        tags = ['VWEAK sab']
        if k >= 3 and b < br[bd[k - 3]]: tags.append('GIRTA (3 din se breadth kam)')
        if k >= 1 and b >= br[bd[k - 1]] + 2: tags.append('PALAT (breadth kal se +2)')
        if k >= 2 and b > br[bd[k - 1]] > br[bd[k - 2]]: tags.append('PALAT2 (2 din se breadth badh rahi)')
        tags.append('level <15' if b < 15 else 'level 15-25')
        state[d] = tags
    log('VWEAK BOUNCE: KAB KAAM KARTA HAI (%s): %s se %s, %d stocks, VWEAK din %d' % (datetime.date.today(), alld[0], alld[-1], len(data), len(state)))
    T = []                                          # (setup, date, rsi, R)
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 70: continue
        b = [byd[x] for x in ds]; o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]
        to = [x[5] for x in b]; rs = rsi(c); e50 = []
        e = None
        for x in c: e = x if e is None else a50 * x + (1 - a50) * e; e50.append(e)
        busy = collections.Counter()
        for i in range(60, len(c) - 1):
            if ds[i] not in state: continue
            if sum(to[i - 20:i]) / 20.0 < 5 or any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 21, i)): continue
            ret3, ret10 = c[i] / c[i - 3] - 1, c[i] / c[i - 10] - 1
            st = []
            if c[i] < e50[i] and rs[i] is not None and rs[i] < 30 and ret3 <= -0.08: st.append('OVERSOLD_BOUNCE')
            if rs[i] is not None and rs[i] < 25 and ret10 <= -0.15: st.append('DEEP_OVERSOLD')
            if c[i] <= c[i - 1] * 0.90: st.append('DROP10')
            if not st: continue
            j = i + 1
            if o[j] > c[i] * 1.015 or o[j] < c[i] * 0.97: continue
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]; atr = sum(tr) / 14.0
            en = o[j]; stop = en - 2 * atr; risk = en - stop
            for s in st:
                if i <= busy[s]: continue
                busy[s] = j + 4
                hold = 3 if s == 'DROP10' else 5
                tp = sum(c[i - 19:i + 1]) / 20.0 if s == 'DROP10' else None
                if tp is not None and tp <= en: tp = None
                ex = None
                for k in range(j, min(len(c), j + hold)):
                    if l[k] <= stop: ex = stop if k == j else min(o[k], stop); break
                    if tp and h[k] >= tp: ex = tp if k == j else max(o[k], tp); break
                if ex is None: ex = c[min(len(c), j + hold) - 1]
                T.append((s, ds[i], rs[i] or 50, (ex - en) / risk - 0.0025 * en / risk))
    def show(title, rows):
        if len(rows) < 20: return
        yrs = collections.defaultdict(list)
        for x in rows: yrs[x[1].year].append(x[3])
        yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
        log('%-52s %6d %4.0f%% %+6.2fR  %d/%d' % (title, len(rows), 100.0 * sum(1 for x in rows if x[3] > 0) / len(rows), sum(x[3] for x in rows) / len(rows), yp, yt))
    for s in ('OVERSOLD_BOUNCE', 'DEEP_OVERSOLD', 'DROP10', 'SAB (teeno)'):
        rows = [x for x in T if s.startswith('SAB') or x[0] == s]
        log(''); log('===== %s =====' % s)
        log('%-52s %6s %5s %7s  %s' % ('market haal', 'n', 'jeet', 'avg R', 'saal+'))
        for tg in ('VWEAK sab', 'GIRTA (3 din se breadth kam)', 'PALAT (breadth kal se +2)', 'PALAT2 (2 din se breadth badh rahi)', 'level <15', 'level 15-25'):
            show(tg, [x for x in rows if tg in state[x[1]]])
        byday = collections.defaultdict(list)
        for x in rows: byday[x[1]].append(x)
        top2 = [y for d in byday for y in sorted(byday[d], key=lambda z: z[2])[:2]]
        show('TOP-2 roz (sabse kam RSI) - VWEAK sab', top2)
        show('TOP-2 roz - sirf PALAT din', [x for x in top2 if 'PALAT (breadth kal se +2)' in state[x[1]]])
        dayR = sorted((d, sum(z[3] for z in v) / len(v), len(v)) for d, v in byday.items())
        if dayR:
            bad = sum(1 for x in dayR if x[1] <= -0.8)
            log('  din-war: %d signal-din, avg din R %+.2f, %d din (%.0f%%) me sab haare (avg <= -0.8R), ek din me signal avg %.1f' % (
                len(dayR), sum(x[1] for x in dayR) / len(dayR), bad, 100.0 * bad / len(dayR), sum(x[2] for x in dayR) / len(dayR)))
            wk = collections.defaultdict(list)
            for d, r_, n in dayR: wk[d.isocalendar()[:2]].append(r_)
            wv = [sum(v) / len(v) for v in wk.values()]
            log('  hafte-war: %d hafte, %d hafte (%.0f%%) bahut bure (avg <= -0.7R) - jaisa 19-23 Oct 2026' % (
                len(wv), sum(1 for x in wv if x <= -0.7), 100.0 * sum(1 for x in wv if x <= -0.7) / max(1, len(wv))))
    open(os.path.join(out_dir, 'turn_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
