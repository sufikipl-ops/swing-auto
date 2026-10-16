# Early vs late breakout entry, and realistic targets. usage: python breakout_study.py <bhav_folder> <out_folder>
# Writes breakout_summary.txt + breakout_results.csv.
# Families (all liquid stocks, uptrend close>EMA50 & EMA20>EMA50):
#  CHASE_FRESH : breakout day (close > prior 20d high, vol>=1.5x, chg>0), close <= 0.5 ATR above old high. Buy-stop at day high*1.001 next day.
#  CHASE_MID   : same but 0.5-1.0 ATR above old high.
#  CHASE_LATE  : same but > 1.0 ATR above old high  (what the app should stop suggesting).
#  PRE_TIGHT   : BEFORE the breakout: close 0-3% (and <=1.5 ATR) below 20d high, last-5-day range < 0.8 ATR, vol5 <= 1.1 x vol20, RSI 50-68.
#                Buy-stop at 20d high*1.001 on next day only.
#  PRE_NEAR    : same without the range/volume squeeze condition.
# Exits: stop = entry - S*ATR, target = entry + T*ATR (or none), hold 5 days. Cost 0.25%, same-bar stop+target = stop.
# R = profit / (S*ATR). Entry skipped if open gaps > 1.5% above the trigger.
import csv, glob, os, sys, datetime, collections

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
COST = 0.25 / 100.0
HOLD = 5
STOPS = [1.5, 2.0]
TARGETS = [1.0, 1.5, 2.0, 3.0, None]
EXITS = [(s, t) for s in STOPS for t in TARGETS]


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


def ema(v, span):
    a = 2.0 / (span + 1); e = v[0]; out = [e]
    for x in v[1:]:
        e = a * x + (1 - a) * e; out.append(e)
    return out


def rsi14(cl):
    out = [None] * len(cl); au = ad = None; n = 0
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]; up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None: au, ad = up, dn
        else:
            au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
        n += 1
        if n >= 14: out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


data = collections.defaultdict(dict)
files = sorted(glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv')))
for f in files:
    with open(f, newline='', encoding='utf-8', errors='ignore') as h:
        rd = csv.reader(h); next(rd, None)
        for r in rd:
            if len(r) < 15 or r[1].strip() != 'EQ': continue
            try:
                d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
            except ValueError:
                continue
            t = tuple(num(r[k]) for k in (4, 5, 6, 8, 10, 11))
            if None in t: continue
            data[r[0].strip()][d] = t
if not data:
    print('no data'); sys.exit(1)
alldates = sorted({d for v in data.values() for d in v})
print('files', len(files), 'symbols', len(data), 'dates', alldates[0], alldates[-1], len(alldates))


def sim(op, hi, lo, cl, j, n, trig, atr, s, t):
    """entry on bar j at max(open, trig) if hi[j] >= trig. returns (R, hit_target) or None"""
    if j >= n or hi[j] < trig: return None
    if op[j] > trig * 1.015: return None
    entry = max(op[j], trig); risk = s * atr; stop = entry - risk
    target = entry + t * atr if t else None
    end = min(j + HOLD, n)
    if end - j < HOLD: return None
    exit_p = None; hit = 0
    for k in range(j, end):
        if k > j and op[k] <= stop: exit_p = op[k]; break
        if lo[k] <= stop: exit_p = stop; break
        if target is not None and hi[k] >= target: exit_p = target; hit = 1; break
    if exit_p is None: exit_p = cl[end - 1]
    return ((exit_p - entry) / risk - COST * entry / risk, hit)


res = collections.defaultdict(lambda: [[] for _ in EXITS])     # fam -> per exit list of (year, R, hit)
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')): continue
    ds = sorted(byd); n = len(ds)
    if n < 130: continue
    op = [byd[d][0] for d in ds]; hi = [byd[d][1] for d in ds]; lo = [byd[d][2] for d in ds]
    cl = [byd[d][3] for d in ds]; vol = [byd[d][4] for d in ds]; to = [byd[d][5] / 100.0 for d in ds]
    e20 = ema(cl, 20); e50 = ema(cl, 50); rs = rsi14(cl)
    tr = [0.0] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    bad = [i for i in range(1, n) if abs(cl[i] / cl[i - 1] - 1) > 0.35]
    bp = 0; last_bad = -10 ** 9
    for i in range(60, n - HOLD - 2):
        while bp < len(bad) and bad[bp] <= i:
            last_bad = bad[bp]; bp += 1
        if last_bad > i - 90: continue
        to20 = sum(to[i - 20:i]) / 20.0
        if to20 < 5 or cl[i] > 6000: continue
        atr = sum(tr[i - 13:i + 1]) / 14.0
        if atr / cl[i] < 0.004: continue
        if not (cl[i] > e50[i] and e20[i] > e50[i]): continue
        y = ds[i].year
        prevhi = max(hi[i - 20:i]); v20 = sum(vol[i - 20:i]) / 20.0
        fam = None; trig = None
        if cl[i] > prevhi and vol[i] >= 1.5 * v20 and cl[i] > cl[i - 1]:
            ext = (cl[i] - prevhi) / atr
            fam = 'CHASE_FRESH' if ext <= 0.5 else ('CHASE_MID' if ext <= 1.0 else 'CHASE_LATE')
            trig = hi[i] * 1.001
            fams = [(fam, trig)]
        else:
            fams = []
            R20 = max(hi[i - 19:i + 1])
            if cl[i] < R20:
                dist = (R20 - cl[i]) / cl[i]
                if dist <= 0.03 and (R20 - cl[i]) <= 1.5 * atr:
                    trig = R20 * 1.001
                    fams.append(('PRE_NEAR', trig))
                    rng5 = sum(hi[k] - lo[k] for k in range(i - 4, i + 1)) / 5.0
                    v5 = sum(vol[i - 4:i + 1]) / 5.0
                    if rng5 < 0.8 * atr and v5 <= 1.1 * v20 and rs[i] is not None and 50 <= rs[i] <= 68:
                        fams.append(('PRE_TIGHT', trig))
        for fam, trig in fams:
            for k, (s, t) in enumerate(EXITS):
                r_ = sim(op, hi, lo, cl, i + 1, n, trig, atr, s, t)
                if r_ is not None: res[fam][k].append((y, r_[0], r_[1]))

years = sorted({d.year for d in alldates})
rows = []
for fam, per in res.items():
    for k, (s, t) in enumerate(EXITS):
        v = per[k]; m = len(v)
        if not m: continue
        vals = [x for _, x, _ in v]
        gp = sum(x for x in vals if x > 0); gl = -sum(x for x in vals if x < 0)
        r = dict(family=fam, stop=s, tgt=t or 0, n=m, win=round(100.0 * sum(1 for x in vals if x > 0) / m),
                 hit=round(100.0 * sum(h for _, _, h in v) / m), avgR=round(sum(vals) / m, 3),
                 pf=round(gp / gl if gl > 0 else 9.99, 2))
        for yy in years:
            yv = [x for y_, x, _ in v if y_ == yy]
            r['R_%d' % yy] = round(sum(yv) / len(yv), 3) if yv else 0.0
        rows.append(r)
with open(os.path.join(out_dir, 'breakout_results.csv'), 'w', newline='', encoding='utf-8') as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

hdr = '%-12s %4s %4s %6s %4s %4s %7s %5s ' % ('family', 'stop', 'tgt', 'n', 'win', 'hit', 'avgR', 'PF') + ' '.join('%7d' % y for y in years)
L = ['BREAKOUT TIMING STUDY (generated %s)' % datetime.date.today().isoformat(),
     'Data %s to %s, %d days, %d symbols. Uptrend + liquid only. Hold 5 days, cost 0.25%%. Stop/target in ATR from entry.' % (
         alldates[0], alldates[-1], len(alldates), len(data)),
     'win = % trades with profit, hit = % trades that reached the target. tgt 0 = no target (exit day 5 close).',
     'CHASE_* = after the breakout day (FRESH <=0.5 ATR above old high, MID 0.5-1, LATE >1). PRE_* = before the breakout.', '', hdr]
for fam in ['PRE_TIGHT', 'PRE_NEAR', 'CHASE_FRESH', 'CHASE_MID', 'CHASE_LATE']:
    for r in sorted([x for x in rows if x['family'] == fam], key=lambda x: (x['stop'], x['tgt'])):
        L.append('%-12s %4.1f %4s %6d %4d %4d %7.3f %5.2f ' % (r['family'], r['stop'], r['tgt'] or '-', r['n'], r['win'], r['hit'],
                 r['avgR'], r['pf']) + ' '.join('%7.3f' % r['R_%d' % y] for y in years))
    L.append('')
L.append('Past results do not guarantee future results.')
open(os.path.join(out_dir, 'breakout_summary.txt'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
