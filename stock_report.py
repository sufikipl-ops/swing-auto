# Builds docs/stocks.json (every NSE EQ stock: EMAs, levels, strength score, buy zone) from bhavcopy.
# usage: python stock_report.py <bhav_folder> <docs_folder>      Read-only, no secrets.
import csv, glob, os, sys, json, datetime, collections

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


def ema(v, span):
    a = 2.0 / (span + 1); e = v[0]; o = [e]
    for x in v[1:]:
        e = a * x + (1 - a) * e; o.append(e)
    return o


def rsi14(cl):
    au = ad = None; n = 0; r = None
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]; up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None:
            au, ad = up, dn
        else:
            au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
        n += 1
        if n >= 14:
            r = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return r


def wilder(v, n=14):
    s = sum(v[:n]); o = [s]
    for x in v[n:]:
        s = s - s / n + x; o.append(s)
    return o


def adx14(hi, lo, cl):
    n = 14
    if len(cl) < 2 * n + 1:
        return None
    pdm, mdm, trl = [], [], []
    for i in range(1, len(cl)):
        up = hi[i] - hi[i - 1]; dn = lo[i - 1] - lo[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
        trl.append(max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])))
    dx = []
    for a, b, c in zip(wilder(trl, n), wilder(pdm, n), wilder(mdm, n)):
        if a == 0:
            dx.append(0.0); continue
        p, m = 100.0 * b / a, 100.0 * c / a
        dx.append(0.0 if p + m == 0 else 100.0 * abs(p - m) / (p + m))
    if len(dx) < n:
        return None
    adx = sum(dx[:n]) / n
    for x in dx[n:]:
        adx = (adx * (n - 1) + x) / n
    return adx


data = collections.defaultdict(dict); alld = set()
for f in glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv')):
    with open(f, newline='', encoding='utf-8', errors='ignore') as h:
        rd = csv.reader(h); next(rd, None)
        for r in rd:
            if len(r) < 15:
                continue
            r = [c.strip() for c in r]
            if r[1] not in ('EQ', 'BE', 'BZ'):
                continue
            try:
                d = datetime.datetime.strptime(r[2], '%d-%b-%Y').date()
            except ValueError:
                continue
            alld.add(d)
            data[r[0]][d] = dict(hi=num(r[5]), lo=num(r[6]), cl=num(r[8]), vol=num(r[10]), to=num(r[11]), dl=num(r[14]))
if not alld:
    print('no bhavcopy'); sys.exit(1)
dates = sorted(alld)[-260:]; last = dates[-1]
out = {}; skip = {}; up = dn = a20 = a50 = tot = 0
KEYS = ('cl', 'hi', 'lo', 'vol', 'to')
for sym, byd in data.items():
    ds = [d for d in dates if d in byd and all(byd[d][k] is not None for k in KEYS)]
    if not ds:
        continue
    lastc = byd[ds[-1]]['cl']
    if ds[-1] != last:
        skip[sym] = ['Aakhri data %s ka hai, aaj ka nahi (suspended/band ya trade nahi hua)' % ds[-1].isoformat(), lastc]
        continue
    cut = 0
    for i in range(1, len(ds)):
        if abs(byd[ds[i]]['cl'] / byd[ds[i - 1]]['cl'] - 1) > 0.35:
            cut = i
    ds = ds[cut:]
    if len(ds) < 60:
        skip[sym] = ['Sirf %d din ka data (60 chahiye)%s' % (len(ds), ', bada jump/split ke baad' if cut else ' (naya listing?)'), lastc]
        continue
    b = [byd[d] for d in ds]
    cl = [x['cl'] for x in b]; hi = [x['hi'] for x in b]; lo = [x['lo'] for x in b]
    vol = [x['vol'] for x in b]; to = [x['to'] / 100.0 for x in b]
    c = cl[-1]; chg = (c / cl[-2] - 1) * 100
    e20, e50 = ema(cl, 20), ema(cl, 50)
    e200 = ema(cl, 200)[-1] if len(cl) >= 150 else None
    r = rsi14(cl); ax = adx14(hi, lo, cl)
    m = [x - y for x, y in zip(ema(cl, 12), ema(cl, 26))]; mh = m[-1] - ema(m, 9)[-1]
    tr = [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, len(cl))]
    atr = sum(tr[-14:]) / 14.0
    prevhi = max(hi[-21:-1]); low5 = min(lo[-5:]); low20 = min(lo[-20:])
    h60 = max(hi[-60:]); h52 = max(hi); l52 = min(lo)
    vx = vol[-1] / (sum(vol[-21:-1]) / 20.0) if sum(vol[-21:-1]) else 0
    to20 = sum(to[-21:-1]) / 20.0
    dl = [x['dl'] for x in b if x['dl'] is not None]
    dla = sum(dl[-21:-1]) / len(dl[-21:-1]) if len(dl) > 21 else None
    tot += 1; up += chg > 0; dn += chg < 0; a20 += c > e20[-1]; a50 += c > e50[-1]
    # strength score (each point is explained to the user)
    why = []; sc = 0
    def pt(ok, txt):
        global sc
        if ok:
            sc += 1; why.append('+ ' + txt)
        else:
            why.append('- NAHI: ' + txt)
    pt(c > e20[-1], 'Price EMA20 ke upar'); pt(c > e50[-1], 'Price EMA50 ke upar')
    pt(e20[-1] > e50[-1], 'EMA20 > EMA50 (uptrend)'); pt(e50[-1] > e50[-6], 'EMA50 upar ja raha hai')
    if e200 is not None:
        pt(c > e200, 'Price EMA200 ke upar (long trend)')
    pt(ax is not None and ax > 20, 'ADX>20 (trend me dum hai)'); pt(mh > 0, 'MACD histogram positive')
    pt(r is not None and 50 <= r <= 72, 'RSI 50-72 (healthy)')
    mx = 8 if e200 is not None else 7
    ratio = sc / float(mx)
    verdict = 'STRONG' if ratio >= 0.75 else ('OK' if ratio >= 0.5 else 'WEAK')
    warn = []
    if r is not None and r > 75: warn.append('Overbought RSI>75')
    if chg > 8: warn.append('Aaj 8%+ bhaga, peecha mat karo')
    if to20 < 5: warn.append('Liquidity kam (20d turnover <5cr)')
    if dla and b[-1]['dl'] is not None and b[-1]['dl'] < 0.6 * dla: warn.append('Delivery kam')
    if c < e50[-1]: warn.append('EMA50 ke niche (weak)')
    if h52 and c >= 0.97 * h52: warn.append('52w high ke paas (resistance/breakout zone)')
    if atr / c > 0.06: warn.append('Bahut volatile (ATR>6%)')
    stop = low5 - 0.1 * atr
    if c - stop > 3 * atr: stop = c - 3 * atr
    if stop >= c: stop = c - 1.5 * atr
    zlo, zhi = e20[-1] * 0.985, e20[-1] * 1.03
    zone = 'IN_ZONE' if zlo <= c <= zhi else ('ABOVE_ZONE' if c > zhi else 'BELOW_ZONE')
    out[sym] = dict(c=round(c, 2), chg=round(chg, 2), e20=round(e20[-1], 2), e50=round(e50[-1], 2),
                    e200=round(e200, 2) if e200 else None, rsi=round(r, 1) if r else None,
                    adx=round(ax, 1) if ax else None, mh=round(mh, 2), atr=round(atr, 2),
                    low5=round(low5, 2), low20=round(low20, 2), h20=round(prevhi, 2), h60=round(h60, 2),
                    h52=round(h52, 2), l52=round(l52, 2), vx=round(vx, 2), t20=round(to20, 1),
                    dl=round(b[-1]['dl'], 1) if b[-1]['dl'] is not None else None, dla=round(dla, 1) if dla else None,
                    score=sc, mx=mx, v=verdict, why=why, warn=warn, stop=round(stop, 2),
                    zlo=round(zlo, 2), zhi=round(zhi, 2), zone=zone, trig=round(prevhi * 1.001, 2))
mk = dict(date=last.isoformat(), n=tot, adv=up, dec=dn, pct20=round(100.0 * a20 / max(tot, 1), 1),
          pct50=round(100.0 * a50 / max(tot, 1), 1))
with open(os.path.join(out_dir, 'stocks.json'), 'w') as h:
    json.dump(dict(market=mk, stocks=out, skip=skip), h, separators=(',', ':'))
print('stocks', len(out), 'skipped', len(skip), '| date', last, '| market', mk)