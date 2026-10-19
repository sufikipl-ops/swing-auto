# Reel "SIBE" (Sweep, Inverse, Break of structure, Entry) - intraday, 15-min (data_orb, F&O stocks ~1 saal).
# Awaaz se rule: pichhle session (yahan: pichhla din) ka high/low mark karo; price unme se ek ko paar kare (sweep),
# phir chhote timeframe par structure ulti taraf toote (BOS) -> entry; SL sweep ke high/low ke paar; target doosri
# taraf ka swing (yahan: pichhle din ka doosra kinara) ya 2R. Intraday: 15:15 candle par band.
# LONG: aaj low < kal ka low (sweep), phir 15-min close kal ke low ke upar AUR sweep ke baad ke pichhle 3 candle ke high ke
#       upar (BOS) -> agli candle ke open par entry. SHORT: ulta (kal ka high). Har stock har din har side max 1 trade.
# Kharcha 0.15% round trip (intraday). Same candle me SL aur target dono = SL (bura maan ke).
# usage: python sibe_study.py   (SYNTH=1 -> random walk sanity)
import os, sys, json, math, random, datetime, collections, csv, traceback

DATA = 'data_orb'
COST = 0.0015
LAST_ENTRY = '14:30'
LINES = []


def log(s=''):
    print(s, flush=True); LINES.append(s)


def load():
    out = {}
    for fn in sorted(os.listdir(DATA)):
        sym = fn[:-5]
        if sym == 'NIFTY_INDEX':
            continue
        by = collections.defaultdict(list)
        for c in json.load(open(os.path.join(DATA, fn))):
            ts = str(c[0]); d, t = ts[:10], ts[11:16]
            if '09:15' <= t <= '15:15' and None not in c[1:5]:
                by[d].append((t, float(c[1]), float(c[2]), float(c[3]), float(c[4])))
        days = [(d, sorted(by[d])) for d in sorted(by) if len(by[d]) >= 20 and sorted(by[d])[-1][0] == '15:15']
        if len(days) > 60:
            out[sym] = days
    return out


def synth(nsym=120, ndays=250):
    """Random walk, har 15-min candle 30 chhote kadmon se (moti candles se jhootha edge na bane)."""
    rnd = random.Random(5); out = {}
    d0 = datetime.date(2025, 1, 1)
    dates = [(d0 + datetime.timedelta(days=k)).isoformat() for k in range(ndays * 2) if (d0 + datetime.timedelta(days=k)).weekday() < 5][:ndays]
    for s in range(nsym):
        px, vol, days = 100 * math.exp(rnd.gauss(0, 1)), rnd.uniform(0.012, 0.03), []
        for d in dates:
            px *= math.exp(rnd.gauss(0, vol * 0.3)); bars = []
            for k in range(25):
                o = px; hi = lo = px
                for _ in range(30):
                    px *= math.exp(rnd.gauss(0, vol / 5 / math.sqrt(30))); hi = max(hi, px); lo = min(lo, px)
                t = (datetime.datetime(2025, 1, 1, 9, 15) + datetime.timedelta(minutes=15 * k)).strftime('%H:%M')
                bars.append((t, o, hi, lo, px))
            days.append((d, bars))
        out['S%03d' % s] = days
    return out


def trade(bars, side, ph, pl, tgt_mode):
    """side 1 = long (kal ke low ka sweep), -1 = short. Return (R_gross, entry, risk) ya None."""
    lvl = pl if side == 1 else ph
    swept, ext = False, None
    for i, (t, o, h, l, c) in enumerate(bars[:-1]):
        if t > LAST_ENTRY:
            return None
        if not swept:
            if (side == 1 and l < lvl) or (side == -1 and h > lvl):
                swept, ext, k = True, (l if side == 1 else h), i
            continue
        ext = min(ext, l) if side == 1 else max(ext, h)
        prev = bars[max(k, i - 3):i]
        if not prev:
            continue
        bos = (c > lvl and c > max(x[2] for x in prev)) if side == 1 else (c < lvl and c < min(x[3] for x in prev))
        if not bos:
            continue
        e = bars[i + 1][1]
        sl = ext * (1 - 0.0005) if side == 1 else ext * (1 + 0.0005)
        risk = (e - sl) * side
        if risk <= e * 0.0015 or risk > e * 0.03:
            return None
        tg = (ph if side == 1 else pl) if tgt_mode == 'PDAY' else e + side * 2 * risk
        if (tg - e) * side <= risk * 0.5:
            tg = e + side * 2 * risk if tgt_mode == 'PDAY' else tg
        for j in range(i + 1, len(bars)):
            _, bo, bh, bl, bc = bars[j]
            hit_sl = bl <= sl if side == 1 else bh >= sl
            hit_tg = bh >= tg if side == 1 else bl <= tg
            if hit_sl:
                ex = (min(bo, sl) if side == 1 else max(bo, sl)) if j > i + 1 else sl
                return ((ex - e) * side / risk, e, risk)
            if hit_tg:
                return ((tg - e) * side / risk, e, risk)
        return ((bars[-1][4] - e) * side / risk, e, risk)
    return None


def main():
    os.makedirs('out', exist_ok=True)
    data = synth() if os.environ.get('SYNTH') else load()
    log('SIBE (sweep -> BOS) INTRADAY STUDY%s (generated %s): %d stocks' % (' [SYNTH]' if os.environ.get('SYNTH') else '', datetime.date.today(), len(data)))
    # market haal: F&O universe me kitne % stock 50-din close avg (EMA) ke upar, kal ke close par
    ab, tot = collections.Counter(), collections.Counter()
    for sym, days in data.items():
        e = None; a = 2.0 / 51
        for k, (d, b) in enumerate(days):
            c = b[-1][4]; e = c if e is None else a * c + (1 - a) * e
            if k >= 50 and k + 1 < len(days):
                nd = days[k + 1][0]; tot[nd] += 1; ab[nd] += c > e
    reg = {d: ('STRONG' if 100.0 * ab[d] / tot[d] >= 60 else 'MIXED' if 100.0 * ab[d] / tot[d] >= 40 else 'WEAK' if 100.0 * ab[d] / tot[d] >= 25 else 'VWEAK')
           for d in tot if tot[d] >= 20}
    dates = sorted(reg); mid = dates[len(dates) // 2] if dates else ''
    R = collections.defaultdict(list)
    for sym, days in data.items():
        for k in range(1, len(days)):
            d, bars = days[k]; pb = days[k - 1][1]
            ph, pl = max(x[2] for x in pb), min(x[3] for x in pb)
            rg = reg.get(d, '?')
            for side in (1, -1):
                for tm in ('PDAY', '2R'):
                    t = trade(bars, side, ph, pl, tm)
                    if t:
                        net = t[0] - COST * t[1] / t[2]
                        for rk in (rg, 'ALL'):
                            R[('LONG' if side == 1 else 'SHORT', tm, rk)].append((d, net, t[0]))
    log('Data %s se %s, aadha %s. R = kharcha (0.15%%) kaat ke; gross = kharche se pehle.' % (dates[0] if dates else '-', dates[-1] if dates else '-', mid))
    log('%-6s %-5s %-7s %6s %5s %8s %8s %8s %8s' % ('side', 'tgt', 'market', 'n', 'jeet', 'avgR', 'gross', 'pehla', 'doosra'))
    rows = []
    for k in sorted(R):
        v = R[k]; n = len(v); rs = [x[1] for x in v]
        h1 = [x[1] for x in v if x[0] < mid]; h2 = [x[1] for x in v if x[0] >= mid]
        row = dict(side=k[0], target=k[1], regime=k[2], n=n, win=round(100.0 * sum(1 for r in rs if r > 0) / n), avgR=round(sum(rs) / n, 3),
                   gross=round(sum(x[2] for x in v) / n, 3), h1=round(sum(h1) / len(h1), 3) if h1 else '', h2=round(sum(h2) / len(h2), 3) if h2 else '')
        rows.append(row)
        log('%-6s %-5s %-7s %6d %4d%% %+8.3f %+8.3f %8s %8s' % (k[0], k[1], k[2], n, row['win'], row['avgR'], row['gross'], row['h1'], row['h2']))
    good = [r for r in rows if r['n'] >= 100 and r['avgR'] > 0.05 and isinstance(r['h1'], float) and r['h1'] > 0 and isinstance(r['h2'], float) and r['h2'] > 0]
    log('')
    log('PASS (n>=100, avgR>+0.05, dono aadhe plus): %s' % (', '.join('%s %s %s %+.3f' % (r['side'], r['target'], r['regime'], r['avgR']) for r in good) or 'koi nahi'))
    suf = '_synth' if os.environ.get('SYNTH') else ''
    open('out/sibe_summary%s.txt' % suf, 'w').write('\n'.join(LINES) + '\n')
    with open('out/sibe_results%s.csv' % suf, 'w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log('ERROR ' + traceback.format_exc()[-800:]); open('out/sibe_summary.txt', 'w').write('\n'.join(LINES) + '\n'); sys.exit(1)
