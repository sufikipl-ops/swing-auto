# DIP setup scan (backtested): strong stock in uptrend that dropped sharply in 3 days.
# Backtest (4 yrs, 1014 days, liquid stocks, 0.25% cost): Tier A win ~61%, avgR +0.165, positive in every year (2025 ~0).
# usage: python dip_scan.py <bhav_folder> <out_folder>   -> writes out/dip_latest.csv and docs/dip_latest.csv
import csv, glob, os, sys, datetime, collections, json, bisect

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
os.makedirs('docs', exist_ok=True)


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
    au = ad = None; n = 0; r = None
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]; up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None: au, ad = up, dn
        else:
            au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
        n += 1
        if n >= 14: r = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return r


data = collections.defaultdict(dict)
alld = set()
for f in glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv')):
    with open(f, newline='', encoding='utf-8', errors='ignore') as h:
        rd = csv.reader(h); next(rd, None)
        for r in rd:
            if len(r) < 15 or r[1].strip() != 'EQ':
                continue
            try:
                d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
            except ValueError:
                continue
            t = [num(r[k]) for k in (5, 6, 8, 10, 11)]
            if None in t:
                continue
            dl = num(r[14])
            data[r[0].strip()][d] = (t[0], t[1], t[2], t[3], t[4], dl)
            alld.add(d)
if not alld:
    print('no bhavcopy'); sys.exit(1)
dates = sorted(alld)[-140:]
last = dates[-1]
ist_today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)).date()
exp = ist_today
ist_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
if ist_now.hour < 18 or (ist_now.hour == 18 and ist_now.minute < 15):
    exp -= datetime.timedelta(days=1)      # NSE file for today comes only after ~6 PM: before that, yesterday's data is the latest
while exp.weekday() >= 5:
    exp -= datetime.timedelta(days=1)
if last < exp:
    print('STALE DATA: latest', last, 'expected', exp); sys.exit(1)

def struct_sig(hi, lo, cl, i, PH, PL, fired):
    """regime_study.py jaisa hi (dono ek saath badalna): fractal swing (2 din dono taraf), higher high + higher low,
    retracement 38%+ jo pichhla higher low na tode, aaj close retracement ke chhote high ke upar. -> (tier, swing_low, depth)"""
    a_, b_ = bisect.bisect_right(PH, i - 2), bisect.bisect_right(PL, i - 2)
    hs = PH[max(0, a_ - 2):a_]; ls = PL[max(0, b_ - 2):b_]
    if len(hs) < 2 or len(ls) < 2: return None
    h1, h2 = hs; l1, l2 = ls
    if not (hi[h2] > hi[h1] and lo[l2] > lo[l1] and l2 < h2 and h1 < l2): return None
    if h2 in fired or h2 >= i - 1: return None
    k = min(range(h2 + 1, i), key=lambda x: lo[x]); m = lo[k]
    if m <= lo[l2] or i - k > 6: return None
    leg = hi[h2] - lo[l2]; depth = (hi[h2] - m) / leg if leg > 0 else 0
    if depth < 0.382: return None
    mh = max(hi[k:i])
    if not (cl[i] > mh and cl[i - 1] <= mh and cl[i] < hi[h2]): return None
    fired.add(h2)
    return ('STRUCT_DEEP' if depth >= 0.618 else 'STRUCT', m, depth)


cands = []
struct = []    # regime_study: market structure setup sirf bahut kamzor market me chala (3/3 saal, n chhota)
bounce = []    # regime_study: oversold bounce sirf bahut kamzor market (breadth<25%) me chala (5/5 saal)
above = tot = 0
labove = ltot = 0   # liquid universe breadth (regime_study jaisa)
r60all = []     # liquid stocks ka 60-din return: momentum (top 20%) tag ke liye
for sym, byd in data.items():
    if any(k in sym for k in ('ETF', 'BEES', 'LIQUID')):
        continue
    ds = [d for d in dates if d in byd]
    if len(ds) < 65 or ds[-1] != last:
        continue
    b = [byd[d] for d in ds]
    hi = [x[0] for x in b]; lo = [x[1] for x in b]; cl = [x[2] for x in b]; vol = [x[3] for x in b]; to = [x[4] / 100.0 for x in b]
    e20 = ema(cl, 20); e50 = ema(cl, 50)
    tot += 1
    if cl[-1] > e50[-1]:
        above += 1
    if any(abs(cl[i] / cl[i - 1] - 1) > 0.35 for i in range(1, len(cl))):
        continue
    to20 = sum(to[-21:-1]) / 20.0
    tr = [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, len(cl))]
    atr = sum(tr[-14:]) / 14.0
    if to20 < 5 or cl[-1] > 6000 or atr / cl[-1] < 0.004:
        continue
    ret3 = cl[-1] / cl[-4] - 1
    ret60 = cl[-1] / cl[-61] - 1
    r60all.append(ret60)
    ltot += 1; labove += cl[-1] > e50[-1]
    n_ = len(cl)
    PH = [p for p in range(2, n_ - 2) if hi[p] > max(hi[p - 2:p]) and hi[p] >= max(hi[p + 1:p + 3])]
    PL = [p for p in range(2, n_ - 2) if lo[p] < min(lo[p - 2:p]) and lo[p] <= min(lo[p + 1:p + 3])]
    fired, st = set(), None
    for i_ in range(max(10, n_ - 40), n_):          # pichhle din bhi chalao taaki 'ek retracement = ek signal' wahi rahe
        r_ = struct_sig(hi, lo, cl, i_, PH, PL, fired)
        st = r_ if i_ == n_ - 1 else None
    if st:
        struct.append(dict(sym=sym, close=cl[-1], chg=(cl[-1] / cl[-2] - 1) * 100, ret3=(cl[-1] / cl[-4] - 1) * 100, ret60=(cl[-1] / cl[-61] - 1) * 100,
                           rsi=rsi14(cl) or 0, atr=atr, e20=e20[-1], e50=e50[-1], vx=vol[-1] / (sum(vol[-21:-1]) / 20.0), to20=to20,
                           kind=st[0], low=st[1], depth=st[2]))
    rsi_ = rsi14(cl); ret10 = cl[-1] / cl[-11] - 1
    if rsi_ is not None and cl[-1] < e50[-1] and ((rsi_ < 30 and ret3 <= -0.08) or (rsi_ < 25 and ret10 <= -0.15)):
        bounce.append(dict(sym=sym, close=cl[-1], chg=(cl[-1] / cl[-2] - 1) * 100, ret3=ret3 * 100, ret10=ret10 * 100, ret60=ret60 * 100,
                           rsi=rsi_, atr=atr, e20=e20[-1], e50=e50[-1], vx=vol[-1] / (sum(vol[-21:-1]) / 20.0), to20=to20,
                           kind='BOUNCE' if (rsi_ < 30 and ret3 <= -0.08) else 'DEEP'))
    rsi = rsi14(cl)
    if rsi is None or ret3 > -0.05:
        continue
    if not (cl[-1] > e50[-1] and e20[-1] > e50[-1] and e50[-1] > e50[-11] and ret60 > 0 and rsi < 45):
        continue
    vx = vol[-1] / (sum(vol[-21:-1]) / 20.0)
    dla = [x[5] for x in b[-21:-1] if x[5] is not None]
    dla = sum(dla) / len(dla) if dla else None
    note = []
    if b[-1][5] is not None and dla and b[-1][5] < 0.6 * dla:
        note.append('LOW_DELIV')
    cands.append(dict(sym=sym, close=cl[-1], chg=(cl[-1] / cl[-2] - 1) * 100, ret3=ret3 * 100, ret60=ret60 * 100, rsi=rsi,
                      atr=atr, e20=e20[-1], e50=e50[-1], vx=vx, to20=to20, dl=b[-1][5], note=' '.join(note)))
breadth = 100.0 * above / tot if tot else 0
# momdip_study (2025-26 test): Dip + 60-din return top 20% = +0.04R vs Dip akela +0.02R (chhota farq, sirf tag)
r60s = sorted(r60all); MOM_CUT = r60s[int(0.8 * len(r60s))] * 100 if r60s else 1e9
rows = []
for c in cands:
    if c['ret3'] <= -8:
        tier = 'A'
    elif breadth >= 50:
        tier = 'B'
    else:
        continue
    stop = c['close'] - 2 * c['atr']
    rows.append([tier, c['sym'], last.isoformat(), round(c['close'], 2), round(c['chg'], 2), round(c['ret3'], 2), round(c['ret60'], 1),
                 round(c['rsi'], 1), round(c['atr'], 2), round(c['e20'], 1), round(c['e50'], 1), round(c['vx'], 2), round(c['to20'], 1),
                 c['dl'] if c['dl'] is not None else '', round(stop, 2), round(c['close'] + 3 * c['atr'], 2), round(breadth, 1), c['note'],
                 1 if c['ret60'] >= MOM_CUT else 0])
lbr = 100.0 * labove / ltot if ltot else 0
REGIME = 'STRONG' if lbr >= 60 else 'MIXED' if lbr >= 40 else 'WEAK' if lbr >= 25 else 'VWEAK'
for c in bounce:
    rows.append([c['kind'], c['sym'], last.isoformat(), round(c['close'], 2), round(c['chg'], 2), round(c['ret3'], 2), round(c['ret60'], 1),
                 round(c['rsi'], 1), round(c['atr'], 2), round(c['e20'], 1), round(c['e50'], 1), round(c['vx'], 2), round(c['to20'], 1),
                 '', round(c['close'] - 2 * c['atr'], 2), round(c['close'] + 3 * c['atr'], 2), round(breadth, 1), 'RET10 %.1f' % c['ret10'], 0])
for c in struct:
    stop = c['low'] * 0.998; risk = c['close'] - stop
    rows.append([c['kind'], c['sym'], last.isoformat(), round(c['close'], 2), round(c['chg'], 2), round(c['ret3'], 2), round(c['ret60'], 1),
                 round(c['rsi'], 1), round(c['atr'], 2), round(c['e20'], 1), round(c['e50'], 1), round(c['vx'], 2), round(c['to20'], 1),
                 '', round(stop, 2), round(c['close'] + 2 * risk, 2), round(breadth, 1), 'DEPTH %.0f' % (c['depth'] * 100), 0])
rows.sort(key=lambda x: ({'A': 0, 'B': 1}.get(x[0], 2), x[5]))
head = ['TIER', 'SYMBOL', 'DATE', 'CLOSE', 'CHG_PCT', 'RET3', 'RET60', 'RSI14', 'ATR14', 'EMA20', 'EMA50', 'VOL_X', 'TURN20_CR',
        'DELIV_PCT', 'STOP_REF', 'TARGET_REF', 'BREADTH50', 'NOTE', 'MOM60_TOP20']
for d in (out_dir, 'docs'):
    with open(os.path.join(d, 'dip_latest.csv'), 'w', newline='', encoding='utf-8') as h:
        w = csv.writer(h); w.writerow(head); w.writerows(rows)
json.dump({'date': last.isoformat(), 'breadth': round(lbr, 1), 'regime': REGIME, 'universe': ltot},
          open(os.path.join('docs', 'regime_today.json'), 'w'))
print('liquid breadth %.1f%% -> %s | bounce candidates %d | structure %d' % (lbr, REGIME, len(bounce), len(struct)))
print('data date', last, '| breadth>EMA50 %.1f%% | 60-din top20%% cut %.1f%% | dip candidates A=%d B=%d' % (
    breadth, MOM_CUT, sum(1 for r in rows if r[0] == 'A'), sum(1 for r in rows if r[0] == 'B')))
