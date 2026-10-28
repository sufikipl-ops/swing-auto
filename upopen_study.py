# User ka pattern (28 Oct 2026): "jo stock uptrend me hai aur subah plus me khule, woh almost pura din plus rehta hai -> subah
# aise stocks me se best pick karke trade". Do hisse:
# A) DAILY (4 saal, liquid stocks, bhavcopy): uptrend (close>EMA20>EMA50, EMA50 upar) + aaj open kal ke close se upar (gap 0-1%,
#    1-3%, 3%+). Entry OPEN par. Nateeja: open->close (din bhar) aur open -> 2/5 din baad close (SL 2 ATR). Tulna: uptrend stock
#    jo neeche khula, aur saare liquid stock.
# B) 15-MIN (F&O ~214 stock, ~1 saal, data_orb): uptrend (pichhle din tak daily EMA20>EMA50) + aaj open > kal close + pehli 15-min
#    candle green + VWAP ke upar -> 9:30 par entry (pehli candle ka close). Exit 15:15 (SL = pehli candle ka low) | 2 din | 5 din.
#    "Best": us din pehle 15 min me sabse zyada chadhe TOP3. Tulna: saare stock 9:30 entry.
# Kharcha: intraday 0.10%, swing 0.25%.
# usage: python upopen_study.py <bhav_folder> <data_orb_folder> <out_folder>
import os, sys, csv, glob, json, random, datetime, collections

LINES = []


def log(s=''):
    print(s, flush=True); LINES.append(s)


def ema(v, n):
    a = 2.0 / (n + 1); e = None; o = []
    for x in v:
        e = x if e is None else a * x + (1 - a) * e; o.append(e)
    return o


def stat(v):
    if not v: return '%6d' % 0
    return '%6d %4.0f%% %+7.2f%%' % (len(v), 100.0 * sum(1 for x in v if x > 0) / len(v), sum(v) / len(v))


def main():
    bhav, orb, out_dir = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else 'out')
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
    log('UPTREND + PLUS OPEN STUDY (%s): daily %s se %s, %d stocks' % (datetime.date.today(), alld[0], alld[-1], len(data)))
    # ---------------- A) daily ----------------
    A = collections.defaultdict(list)
    uptr = {}                                  # (sym, date) -> uptrend as of prev close (15-min part ke liye)
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 70: continue
        b = [byd[x] for x in ds]; o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]; to = [x[5] for x in b]
        e20, e50 = ema(c, 20), ema(c, 50)
        for i in range(60, len(c) - 1):
            up = c[i - 1] > e20[i - 1] > e50[i - 1] and e50[i - 1] > e50[i - 11]
            uptr[(sym, ds[i])] = up
            if sum(to[i - 21:i - 1]) / 20.0 < 5 or c[i - 1] > 6000 or any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 20, i + 1)):
                continue
            gap = (o[i] / c[i - 1] - 1) * 100
            tags = ['SAB liquid stock']
            if up:
                tags.append('UPTREND (sab)')
                if gap > 0: tags.append('UPTREND + plus open (gap>0)')
                if 0 < gap <= 1: tags.append('UPTREND + gap 0-1%')
                if 1 < gap <= 3: tags.append('UPTREND + gap 1-3%')
                if gap > 3: tags.append('UPTREND + gap 3%+')
                if gap <= 0: tags.append('UPTREND + neeche/flat open')
            tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 14, i)]; atr = sum(tr) / 14.0
            en = o[i]; stop = en - 2 * atr
            res = {'din bhar (open->close)': (c[i] / en - 1) * 100 - 0.10}
            for hold in (2, 5):
                ex = None
                for k in range(i, min(len(c), i + hold)):
                    if l[k] <= stop: ex = stop if k == i else min(o[k], stop); break
                if ex is None: ex = c[min(len(c), i + hold) - 1]
                res['%d din (SL 2ATR)' % hold] = (ex / en - 1) * 100 - 0.25
            rg = reg.get(ds[i], '?')
            for t in tags:
                for k_, v_ in res.items():
                    A[(t, k_, 'ALL')].append(v_); A[(t, k_, rg)].append(v_)
                A[(t, 'din plus band (close>open)', 'ALL')].append(1 if c[i] > en else -1)
    log(''); log('===== A) DAILY: entry subah OPEN par (4 saal) =====')
    for k_ in ('din bhar (open->close)', '2 din (SL 2ATR)', '5 din (SL 2ATR)'):
        log(''); log('-- %s --' % k_)
        log('%-30s %-7s %6s %5s %8s' % ('group', 'market', 'n', 'jeet', 'avg%'))
        for t in ('SAB liquid stock', 'UPTREND (sab)', 'UPTREND + plus open (gap>0)', 'UPTREND + gap 0-1%', 'UPTREND + gap 1-3%',
                  'UPTREND + gap 3%+', 'UPTREND + neeche/flat open'):
            for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
                v = A.get((t, k_, rk))
                if v and (rk == 'ALL' or len(v) >= 100): log('%-30s %-7s %s' % (t, rk, stat(v)))
    # ---------------- B) 15-min ----------------
    days15 = {}
    for fn in sorted(os.listdir(orb)):
        sym = fn[:-5]; by = collections.defaultdict(list)
        for cn in json.load(open(os.path.join(orb, fn))):
            ts = str(cn[0]); d, t = ts[:10], ts[11:16]
            if '09:15' <= t <= '15:15' and None not in cn[1:5]:
                by[d].append((t, float(cn[1]), float(cn[2]), float(cn[3]), float(cn[4]), float(cn[5] or 0)))
        days15[sym] = {d: sorted(v) for d, v in by.items() if len(v) >= 20}
    B = collections.defaultdict(list); rnd = random.Random(3)
    per_day = collections.defaultdict(list)
    for sym, byd in days15.items():
        dl = sorted(byd)
        for k in range(1, len(dl) - 5):
            d, cs = dl[k], byd[dl[k]]
            pc = byd[dl[k - 1]][-1][4]
            dd = datetime.date.fromisoformat(d)
            up = uptr.get((sym, dd))
            if up is None: continue
            c0 = cs[0]; en = c0[4]; lo0 = c0[3]
            vw = sum((x[2] + x[3] + x[4]) / 3 * x[5] for x in cs[:1]) / max(1, sum(x[5] for x in cs[:1]))
            g1 = (en / pc - 1) * 100
            ok = up and c0[1] > pc and c0[4] > c0[1] and en >= vw
            # exit 15:15 / SL pehli candle ka low
            ex = None
            for x in cs[1:]:
                if x[3] <= lo0: ex = lo0; break
            if ex is None: ex = cs[-1][4]
            r_day = (ex / en - 1) * 100 - 0.10
            r2 = (byd[dl[k + 1]][-1][4] / en - 1) * 100 - 0.25
            r5 = (byd[dl[k + 4]][-1][4] / en - 1) * 100 - 0.25
            rec = (g1, r_day, r2, r5, dd)
            B['SAB stock (9:30 entry)'].append(rec)
            if up: B['UPTREND (sab)'].append(rec)
            if ok:
                B['UPTREND + plus open + green 15m + VWAP upar'].append(rec); per_day[d].append(rec)
    for d, L in per_day.items():
        for rec in sorted(L, key=lambda x: -x[0])[:3]: B['  ... TOP3 (pehle 15 min sabse tez)'].append(rec)
        for rec in sorted(L, key=lambda x: x[0])[:3]: B['  ... BOTTOM3 (sabse dheema)'].append(rec)
    log(''); log('===== B) 15-MIN (F&O, %d stock): entry 9:30 (pehli candle close) =====' % len(days15))
    log('%-46s | %-22s | %-22s | %-22s' % ('group', 'aaj 15:15 (SL 1st low)', '2 din (close)', '5 din (close)'))
    for t in ('SAB stock (9:30 entry)', 'UPTREND (sab)', 'UPTREND + plus open + green 15m + VWAP upar', '  ... TOP3 (pehle 15 min sabse tez)', '  ... BOTTOM3 (sabse dheema)'):
        v = B.get(t, [])
        log('%-46s | %s | %s | %s' % (t, stat([x[1] for x in v]), stat([x[2] for x in v]), stat([x[3] for x in v])))
        if t.startswith('UPTREND + plus'):
            h1 = [x for x in v if x[4] < datetime.date(2026, 4, 15)]; h2 = [x for x in v if x[4] >= datetime.date(2026, 4, 15)]
            log('%-46s | %s | %s | %s' % ('    (pehla aadha)', stat([x[1] for x in h1]), stat([x[2] for x in h1]), stat([x[3] for x in h1])))
            log('%-46s | %s | %s | %s' % ('    (doosra aadha)', stat([x[1] for x in h2]), stat([x[2] for x in h2]), stat([x[3] for x in h2])))
    open(os.path.join(out_dir, 'upopen_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
