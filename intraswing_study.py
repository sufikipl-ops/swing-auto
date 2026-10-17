# Live (din ke andar) setup study: kya breakout / reversal / dip / bounce ko DIN ME pakad ke 3:15 baje entry lena
# kal subah (next open) ki entry se behtar hai? Har market haal (breadth) me alag.
# Data: Angel 15-min candles (data_orb/, orb_study ka cache, F&O stocks ~1 saal). Swing exit dono me same:
# SL 2 ATR (entry se), max 5 din (5th din close), kharcha 0.25% round trip. Sirf long (cash me raat bhar short nahi).
# "3:15 entry": signal 15:15 tak ke data se (aakhri 15:15 candle ko chhod ke), entry 15:15 candle ke open par.
# "Kal open": wahi setup poore din ke close se, entry agle din open par, gap filter (+1.5% / -3%) ke saath.
# usage: python intraswing_study.py   (SYNTH=1 -> random walk data par sanity check, edge ~0 aana chahiye)
import os, sys, json, math, random, datetime, collections, csv, traceback

DATA = 'data_orb'
COST = 0.0025
HOLD = 5
LINES = []


def log(s):
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
            if '09:15' <= t <= '15:15' and None not in c[1:6]:
                by[d].append((t, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5] or 0)))
        days = []
        for d in sorted(by):
            b = sorted(by[d])
            if len(b) < 20 or b[-1][0] != '15:15':
                continue
            pre = [x for x in b if x[0] < '15:15']
            days.append(dict(d=d, O=b[0][1], H=max(x[2] for x in b), L=min(x[3] for x in b), C=b[-1][4], V=sum(x[5] for x in b),
                             P=b[-1][1], Hs=max(x[2] for x in pre), Ls=min(x[3] for x in pre), Vs=sum(x[5] for x in pre),
                             l15=b[-1][3], c15=b[-1][4]))
        if len(days) > 80:
            out[sym] = days
    return out


def synth(nsym=150, ndays=300):
    """Random walk 15-min candles: koi edge nahi. Study ko yahan ~ -kharcha dena chahiye."""
    rnd = random.Random(7); out = {}
    d0 = datetime.date(2025, 1, 1)
    dates = [(d0 + datetime.timedelta(days=k)).isoformat() for k in range(ndays * 2) if (d0 + datetime.timedelta(days=k)).weekday() < 5][:ndays]
    for s in range(nsym):
        px, vol, days = 100 * math.exp(rnd.gauss(0, 1)), rnd.uniform(0.012, 0.03), []
        for d in dates:
            px *= math.exp(rnd.gauss(0, vol * 0.3))            # overnight gap
            bars = []
            for k in range(25):
                o = px; px *= math.exp(rnd.gauss(0, vol / 5)); c = px
                h = max(o, c) * math.exp(abs(rnd.gauss(0, vol / 10))); l = min(o, c) * math.exp(-abs(rnd.gauss(0, vol / 10)))
                bars.append((k, o, h, l, c, rnd.lognormvariate(10, 0.6)))
            pre = bars[:-1]
            days.append(dict(d=d, O=bars[0][1], H=max(x[2] for x in bars), L=min(x[3] for x in bars), C=bars[-1][4], V=sum(x[5] for x in bars),
                             P=bars[-1][1], Hs=max(x[2] for x in pre), Ls=min(x[3] for x in pre), Vs=sum(x[5] for x in pre),
                             l15=bars[-1][3], c15=bars[-1][4]))
        out['S%03d' % s] = days
    return out


def ema(a, n):
    k, e, o = 2.0 / (n + 1), a[0], []
    for x in a:
        e = x * k + e * (1 - k); o.append(e)
    return o


def rsi_last(cl):
    au = ad = None
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]; up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None:
            au, ad = up, dn
        else:
            au = au * 13 / 14.0 + up / 14.0; ad = ad * 13 / 14.0 + dn / 14.0
    return 100.0 if not ad else 100 - 100 / (1 + au / ad)


def setups(pc, H, L, V, C_hist, i, atr, e50, e20, hi20, av20, ret3, ret60, rsi, vol_frac):
    """pc = abhi ka bhav (3:15 snapshot ya din ka close), H/L/V = ab tak ka din. Return list of setup names."""
    s, prev = [], C_hist[i - 1]
    up = pc > e50 and e20 > e50
    if pc > hi20 and up and V >= 1.5 * av20 * vol_frac and rsi < 75 and (H - L) > 0 and (pc - L) / (H - L) >= 0.6:
        s.append('BREAKOUT')
    fall = (prev - L) / atr
    if fall >= 1.5 and (pc - L) >= 0.6 * (prev - L) and V >= av20 * vol_frac:
        s.append('REVERSAL_UP' if pc > e50 else 'REVERSAL_DOWNTREND')
    if ret3 <= -0.08 and up and ret60 > 0 and rsi < 45:
        s.append('DIP_A')
    if pc < e50 and rsi < 30 and ret3 <= -0.08:
        s.append('BOUNCE')
    return s


def exit_r(days, i, entry, stop, risk, same_day_low=None):
    """Entry din i par (3:15) ya din i ka open (next-open). Days i+1.. tak, max HOLD din."""
    if same_day_low is not None and same_day_low <= stop:
        return (stop - entry) / risk - COST * entry / risk
    last = min(i + HOLD, len(days) - 1)
    for j in range(i + 1, last + 1):
        dj = days[j]
        if dj['O'] <= stop:
            return (dj['O'] - entry) / risk - COST * entry / risk
        if dj['L'] <= stop:
            return (stop - entry) / risk - COST * entry / risk
    return (days[last]['C'] - entry) / risk - COST * entry / risk


def run(data):
    # breadth (universe ke % stock EMA50 ke upar, kal ke close par) har date ke liye
    ab, tot = collections.Counter(), collections.Counter()
    E = {}
    for sym, days in data.items():
        cl = [x['C'] for x in days]; E[sym] = (ema(cl, 50), ema(cl, 20))
        for k in range(60, len(days)):
            tot[days[k]['d']] += 1; ab[days[k]['d']] += cl[k] > E[sym][0][k]
    br = {d: 100.0 * ab[d] / tot[d] for d in tot if tot[d] >= 20}
    dates = sorted(br)
    prevbr = {dates[k]: br[dates[k - 1]] for k in range(1, len(dates))}

    def reg(b):
        return 'STRONG' if b >= 60 else 'MIXED' if b >= 40 else 'WEAK' if b >= 25 else 'VWEAK'
    rc = collections.Counter(reg(v) for v in prevbr.values())
    log('Din har market haal me (F&O universe breadth): %s' % dict(rc))
    mid = dates[len(dates) // 2] if dates else ''
    R = collections.defaultdict(list)                     # (setup, timing, regime) -> [(date, r)]
    base = collections.defaultdict(list)                  # (timing, regime) -> r
    skipped_split = 0
    for sym, days in data.items():
        cl = [x['C'] for x in days]; e50, e20 = E[sym]
        for i in range(61, len(days) - 1):
            d = days[i]
            if d['d'] not in prevbr:
                continue
            rg = reg(prevbr[d['d']])
            w = days[max(0, i - 60): min(len(days), i + HOLD + 2)]
            if any(abs(w[k]['O'] / w[k - 1]['C'] - 1) > 0.25 for k in range(1, len(w))):
                skipped_split += 1; continue
            tr = [max(days[k]['H'] - days[k]['L'], abs(days[k]['H'] - days[k - 1]['C']), abs(days[k]['L'] - days[k - 1]['C'])) for k in range(i - 14, i)]
            atr = sum(tr) / 14.0
            if atr <= 0 or atr / cl[i - 1] < 0.004:
                continue
            hi20 = max(x['H'] for x in days[i - 20:i]); av20 = sum(x['V'] for x in days[i - 20:i]) / 20.0
            if av20 * cl[i - 1] < 5e7:                    # 5 cr/din se kam turnover: skip
                continue
            risk = 2 * atr
            # ---- 3:15 snapshot ----
            P = d['P']
            sn = setups(P, d['Hs'], d['Ls'], d['Vs'], cl, i, atr, e50[i - 1], e20[i - 1], hi20, av20,
                        P / cl[i - 3] - 1, P / cl[i - 60] - 1, rsi_last(cl[i - 40:i] + [P]), 0.92)
            r315 = exit_r(days, i, P, P - risk, risk, same_day_low=d['l15'])
            base[('3:15', rg)].append(r315)
            for s in sn:
                R[(s, '3:15', rg)].append((d['d'], r315))
            # ---- din ka close -> kal open ----
            C = d['C']
            se = setups(C, d['H'], d['L'], d['V'], cl, i, atr, e50[i - 1], e20[i - 1], hi20, av20,
                        C / cl[i - 3] - 1, C / cl[i - 60] - 1, rsi_last(cl[i - 40:i + 1]), 1.0)
            o = days[i + 1]['O']
            gap_ok = C * 0.97 <= o <= C * 1.015
            rno = exit_r(days, i + 1, o, o - risk, risk, same_day_low=days[i + 1]['L']) if gap_ok else None
            if rno is not None:
                base[('Kal open', rg)].append(rno)
                for s in se:
                    R[(s, 'Kal open', rg)].append((d['d'], rno))
    log('split/bade gap wale windows skip: %d' % skipped_split)
    log('Test period: %s se %s (aadha: %s)' % (dates[0] if dates else '-', dates[-1] if dates else '-', mid))
    log('')
    log('Base = har liquid stock har din (koi setup nahi), wahi exit: market ka apna asar.')
    for k in sorted(base):
        a = base[k]; log('  base %-8s %-7s n=%6d avgR %+.3f' % (k[0], k[1], len(a), sum(a) / len(a)))
    log('')
    log('%-20s %-8s %-7s %5s %5s %7s %7s %7s %7s  %s' % ('setup', 'entry', 'market', 'n', 'jeet%', 'avgR', 'pehla', 'doosra', 'base', 'pass?'))
    rows = []
    for k in sorted(R, key=lambda k: (k[0], k[2], k[1])):
        a = R[k]; rs = [r for _, r in a]; n = len(rs)
        h1 = [r for dd, r in a if dd < mid]; h2 = [r for dd, r in a if dd >= mid]
        av = sum(rs) / n; bs = base[(k[1], k[2])]; bav = sum(bs) / len(bs) if bs else 0
        a1 = sum(h1) / len(h1) if h1 else None; a2 = sum(h2) / len(h2) if h2 else None
        ok = n >= 40 and av >= 0.05 and (a1 or 0) > 0 and (a2 or 0) > 0 and av - bav >= 0.05 and len(h1) >= 10 and len(h2) >= 10
        win = 100.0 * sum(1 for r in rs if r > 0) / n
        rows.append(dict(setup=k[0], entry=k[1], regime=k[2], n=n, win=round(win), avgR=round(av, 3),
                         h1=None if a1 is None else round(a1, 3), h2=None if a2 is None else round(a2, 3), base=round(bav, 3), ok=ok))
        log('%-20s %-8s %-7s %5d %5.0f %+7.3f %7s %7s %+7.3f  %s' % (k[0], k[1], k[2], n, win, av,
            '-' if a1 is None else '%+.3f' % a1, '-' if a2 is None else '%+.3f' % a2, bav, 'PASS' if ok else ''))
    log('')
    log('PASS rule: n>=40, avgR>=+0.05, dono aadhe plus, aur base se 0.05R+ behtar. Data ~1 saal (F&O stocks), isliye nateeja kachha hai.')
    return rows


def main():
    os.makedirs('out', exist_ok=True)
    if os.environ.get('SYNTH'):
        log('SYNTH random walk sanity check'); data = synth()
    else:
        if not os.path.isdir(DATA) or len(os.listdir(DATA)) < 50:
            sys.path.insert(0, '.'); import orb_study
            orb_study.fetch_all(); LINES.extend(orb_study.LINES)
        data = load()
    log('stocks loaded: %d' % len(data))
    rows = run(data)
    suf = '_synth' if os.environ.get('SYNTH') else ''
    open('out/intraswing_summary%s.txt' % suf, 'w').write('\n'.join(LINES) + '\n')
    if rows:
        with open('out/intraswing_results%s.csv' % suf, 'w', newline='') as h:
            w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log('ERROR ' + traceback.format_exc()[-800:])
        open('out/intraswing_summary.txt', 'w').write('\n'.join(LINES) + '\n'); sys.exit(1)
