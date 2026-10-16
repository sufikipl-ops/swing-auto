# Swing screen: reads daily NSE bhavcopy files, writes screen_latest.csv (BREAKOUT / PULLBACK candidates)
# usage: python screen.py <bhav_folder> <output_folder>
import csv, glob, os, sys, datetime, collections

bhav_dir = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)


def num(x):
    x = str(x).strip()
    try:
        return float(x)
    except ValueError:
        return None


def ema(vals, span):
    a = 2.0 / (span + 1)
    e = vals[0]
    out = [e]
    for v in vals[1:]:
        e = a * v + (1 - a) * e
        out.append(e)
    return out


def rsi14(cl):
    au = ad = None
    n = 0
    rsi = None
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]
        up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None:
            au, ad = up, dn
        else:
            au = (1 - 1 / 14.0) * au + (1 / 14.0) * up
            ad = (1 - 1 / 14.0) * ad + (1 / 14.0) * dn
        n += 1
        if n >= 14:
            rsi = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return rsi


def wilder(vals, n=14):
    s = sum(vals[:n])
    out = [s]
    for v in vals[n:]:
        s = s - s / n + v
        out.append(s)
    return out


def adx14(hi, lo, cl):
    n = 14
    if len(cl) < 2 * n + 1:
        return None, None, None
    pdm, mdm, trl = [], [], []
    for i in range(1, len(cl)):
        up = hi[i] - hi[i - 1]
        dn = lo[i - 1] - lo[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
        trl.append(max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])))
    st, sp, sm = wilder(trl, n), wilder(pdm, n), wilder(mdm, n)
    dx = []
    pdi = mdi = None
    for a, b, c in zip(st, sp, sm):
        if a == 0:
            dx.append(0.0)
            continue
        pdi = 100.0 * b / a
        mdi = 100.0 * c / a
        s = pdi + mdi
        dx.append(0.0 if s == 0 else 100.0 * abs(pdi - mdi) / s)
    if len(dx) < n:
        return None, None, None
    adx = sum(dx[:n]) / n
    for v in dx[n:]:
        adx = (adx * (n - 1) + v) / n
    return adx, pdi, mdi


def macd_hist(cl):
    m = [a - b for a, b in zip(ema(cl, 12), ema(cl, 26))]
    s = ema(m, 9)
    return m[-1], s[-1], m[-1] - s[-1]


# ---- load: EQ series only, de-duplicate by date inside the file (holiday files repeat the previous day)
data = collections.defaultdict(dict)      # symbol -> {date: row}
alldates = set()
for f in glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv')):
    with open(f, newline='', encoding='utf-8', errors='ignore') as h:
        rd = csv.reader(h)
        header = next(rd, None)
        for r in rd:
            if len(r) < 15:
                continue
            r = [c.strip() for c in r]
            if r[1] != 'EQ':
                continue
            try:
                d = datetime.datetime.strptime(r[2], '%d-%b-%Y').date()
            except ValueError:
                continue
            alldates.add(d)
            data[r[0]][d] = dict(
                hi=num(r[5]), lo=num(r[6]), cl=num(r[8]), vol=num(r[10]),
                to=num(r[11]), dl=num(r[14]))

if not alldates:
    print('no bhavcopy files found in', bhav_dir); sys.exit(1)
dates = sorted(alldates)[-90:]
last = dates[-1]

# freshness check: data date must be the latest trading day (IST)
ist_today = (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).date()
expected = ist_today
while expected.weekday() >= 5:
    expected -= datetime.timedelta(days=1)
ld = last.date() if isinstance(last, datetime.datetime) else last
if ld < expected:
    print('STALE DATA: latest', ld, 'expected', expected)
    sys.exit(1)

rows = []
for sym, byd in data.items():
    ds = [d for d in dates if d in byd]
    if len(ds) < 45 or ds[-1] != last:
        continue
    bars = [byd[d] for d in ds]
    if any(b['cl'] is None or b['hi'] is None or b['lo'] is None or b['vol'] is None or b['to'] is None for b in bars):
        continue
    cl = [b['cl'] for b in bars]
    if any(abs(cl[i] / cl[i - 1] - 1) > 0.35 for i in range(1, len(cl))):
        continue                                 # likely split/bonus distortion
    hi = [b['hi'] for b in bars]; lo = [b['lo'] for b in bars]
    vol = [b['vol'] for b in bars]; to = [b['to'] / 100.0 for b in bars]   # crore
    dl = [b['dl'] for b in bars if b['dl'] is not None]
    e20 = ema(cl, 20); e50 = ema(cl, 50)
    r = rsi14(cl)
    if r is None:
        continue
    adx_v, pdi_v, mdi_v = adx14(hi, lo, cl)
    macd_v, macd_sig, macd_h = macd_hist(cl)
    prevhi = max(hi[-21:-1])
    vx = vol[-1] / (sum(vol[-21:-1]) / 20.0)
    to20 = sum(to[-21:-1]) / 20.0
    chg = (cl[-1] / cl[-2] - 1) * 100
    tr = [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, len(cl))]
    atr = sum(tr[-14:]) / 14.0
    del_t = bars[-1]['dl']
    del_a = (sum(dl[-21:-1]) / len(dl[-21:-1])) if len(dl) > 21 else None
    upper_ckt = (cl[-1] >= hi[-1] - 0.01) and any(lo_ <= chg <= hi_ for lo_, hi_ in [(4.8, 5.05), (9.8, 10.05), (19.8, 20.05)])
    if to20 < 5 or upper_ckt or cl[-1] > 6000:
        continue
    if atr / cl[-1] < 0.004 or any(k in sym for k in ('ETF', 'BEES', 'LIQUID')):
        continue                                 # ETFs / liquid funds
    setup = ''
    if cl[-1] > prevhi and vx >= 1.5 and cl[-1] > e50[-1] and chg > 0 and e20[-1] > e50[-1]:
        setup = 'BREAKOUT'
    elif (e20[-1] * 0.985 <= cl[-1] <= e20[-1] * 1.03 and e20[-1] > e50[-1] and cl[-1] > e50[-1]
          and 38 <= r <= 52 and e50[-1] > e50[-6]):
        setup = 'PULLBACK'
    r20 = max(hi[-20:])
    v20 = sum(vol[-21:-1]) / 20.0
    if not setup and cl[-1] < r20 and cl[-1] > e50[-1] and e20[-1] > e50[-1] and e50[-1] > e50[-6] and 50 <= r <= 68 and chg < 4:
        # BEFORE the breakout: just under the 20-day high, range squeezed, volume quiet
        rng5 = sum(hi[k] - lo[k] for k in range(-5, 0)) / 5.0
        v5 = sum(vol[-5:]) / 5.0
        if 0 < (r20 - cl[-1]) <= 1.0 * atr and (r20 - cl[-1]) / cl[-1] <= 0.03 and rng5 < 0.8 * atr and v5 <= 1.1 * v20:
            setup = 'PREBREAK'
    if not setup:
        continue
    ext = (cl[-1] - prevhi) / atr if setup == 'BREAKOUT' else 0.0
    entry = (r20 if setup == 'PREBREAK' else hi[-1]) * 1.001
    note = []
    if setup == 'BREAKOUT' and ext > 1.0: note.append('LATE')     # already ran >1 ATR past the old high: do not chase
    if del_t is not None and del_a and del_t < 0.6 * del_a: note.append('LOW_DELIV')
    if r > 70 or chg > 8: note.append('EXTENDED')
    rows.append([setup, sym, last.isoformat(), round(cl[-1], 2), round(chg, 2), hi[-1], lo[-1], round(prevhi, 2),
                 round(e20[-1], 1), round(e50[-1], 1), round(r, 1), round(vx, 2), round(to[-1], 1), round(to20, 1),
                 del_t if del_t is not None else '', round(del_a, 1) if del_a else '', round(atr, 1),
                 min(lo[-5:]), max(hi[-60:]), ' '.join(note),
                 round(adx_v, 1) if adx_v is not None else '', round(macd_h, 2), round(entry, 2), round(ext, 2), round(r20, 2)])

rows.sort(key=lambda x: ('LATE' in x[19], -x[12]))                 # fresh setups first, late breakouts last
rows = ([x for x in rows if x[0] == 'BREAKOUT'][:25] + [x for x in rows if x[0] == 'PREBREAK'][:25]
        + [x for x in rows if x[0] == 'PULLBACK'][:25])
head = ['SETUP', 'SYMBOL', 'DATE', 'CLOSE', 'CHG_PCT', 'DAY_HIGH', 'DAY_LOW', 'H20_PREV', 'EMA20', 'EMA50', 'RSI14',
        'VOL_X', 'TURN_CR', 'TURN20_CR', 'DELIV_PCT', 'DELIV20_PCT', 'ATR14', 'LOW5', 'HIGH60', 'NOTE',
        'ADX14', 'MACD_H', 'ENTRY', 'EXT_ATR', 'R20']
for name in ('screen_latest.csv', 'screen_%s.csv' % last.strftime('%Y%m%d')):
    with open(os.path.join(out_dir, name), 'w', newline='', encoding='utf-8') as h:
        w = csv.writer(h); w.writerow(head); w.writerows(rows)
print('data date', last, '| days loaded', len(dates), '| candidates', len(rows))
