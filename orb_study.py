# Intraday "NSE heatmap + 15 min breakout + 8 EMA" (Opening Range Breakout) backtest on F&O stocks.
# Rules (Instagram reel PDF): market green (red for short), candle closes above 15-min opening-range high (below low
# for short) as a green (red) candle beyond the 8 EMA, entry when the NEXT candle breaks that candle's high (low),
# SL = breakout candle low (high), target 1.5R or 2R, square off at 15:15. One trade per stock per side per day.
# Data: Angel One SmartAPI 15-min candles (~1 year), cached in data_orb/. Needs ANGEL_* secrets (GitHub Actions).
# usage: python orb_study.py   -> out/orb_summary.txt, out/orb_results.csv, out/orb_trades.csv (main config)
import os, sys, json, time, datetime, collections, csv, traceback
import urllib.request

from angel_gap import totp, call, BASE, MASTER

DATA = 'data_orb'
DAYS = int(os.environ.get('ORB_DAYS', '370'))
COSTS = [0.0, 0.0015]            # round trip: 0 = edge before costs; 0.15% = brokerage+STT+charges+slippage
TARGETS = [1.5, 2.0, 3.0]        # 3.0 = video ki awaaz me bola '1:3 target'
LAST_ENTRY = '14:30'             # breakout candle must start by this time
LINES = []


def log(s):
    print(s, flush=True); LINES.append(s)


# ---------------- fetch ----------------
def fetch_all():
    key, cid = os.environ.get('ANGEL_API_KEY', '').strip(), os.environ.get('ANGEL_CLIENT_ID', '').strip()
    pin, tsec = os.environ.get('ANGEL_PIN', '').strip(), os.environ.get('ANGEL_TOTP_SECRET', '').strip()
    if not (key and cid and pin and tsec):
        log('Angel secrets missing: using only cached data_orb/'); return
    res = call(key, BASE + '/rest/auth/angelbroking/user/v1/loginByPassword', {'clientcode': cid, 'password': pin, 'totp': totp(tsec)})
    if not res.get('status') or not res.get('data'):
        log('LOGIN FAIL: %s' % res.get('message')); return
    jwt = res['data']['jwtToken']
    with urllib.request.urlopen(MASTER, timeout=180) as r:
        master = json.loads(r.read().decode())
    fno = sorted({m['name'] for m in master if m.get('exch_seg') == 'NFO' and m.get('instrumenttype') == 'FUTSTK'})
    eq = {m['symbol']: m['token'] for m in master if m.get('exch_seg') == 'NSE' and m['symbol'].endswith('-EQ')}
    idx = next((m['token'] for m in master if m.get('exch_seg') == 'NSE' and m.get('symbol') in ('Nifty 50', 'NIFTY 50')), '99926000')
    syms = [(s, eq[s + '-EQ']) for s in fno if s + '-EQ' in eq] + [('NIFTY_INDEX', idx)]
    log('F&O stocks in master: %d (with NSE EQ token: %d)' % (len(fno), len(syms) - 1))
    os.makedirs(DATA, exist_ok=True)
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).date()
    wins, end = [], today
    while (today - end).days < DAYS:                     # 15-min: max ~200 din per request
        st = max(end - datetime.timedelta(days=180), today - datetime.timedelta(days=DAYS))
        wins.append((st, end)); end = st - datetime.timedelta(days=1)
    got = fail = upd = 0
    for sym, tok in syms:
        p = os.path.join(DATA, sym + '.json')
        old, ws = [], wins
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            try:
                old = json.load(open(p))
            except Exception:
                old = []
        if old:                                           # purani file: sirf aakhri din ke baad ka naya data jodo
            last = datetime.date.fromisoformat(str(old[-1][0])[:10])
            if (today - last).days < 1:
                continue
            ws, end = [], today
            while end >= last:
                st = max(end - datetime.timedelta(days=180), last)
                ws.append((st, end)); end = st - datetime.timedelta(days=1)
        cs = []
        for st, en in ws:
            for attempt in range(4):
                r = call(key, BASE + '/rest/secure/angelbroking/historical/v1/getCandleData',
                         {'exchange': 'NSE', 'symboltoken': tok, 'interval': 'FIFTEEN_MINUTE',
                          'fromdate': st.strftime('%Y-%m-%d') + ' 09:15', 'todate': en.strftime('%Y-%m-%d') + ' 15:30'}, jwt)
                if r.get('status'):
                    cs += r.get('data') or []; break
                time.sleep(3 + 4 * attempt)               # access-rate limit: ruk ke dobara
            time.sleep(0.8)
        if cs:
            json.dump(sorted({c[0]: c for c in old + cs}.values()), open(p, 'w'))
            if old:
                upd += 1
            else:
                got += 1
        elif not old:
            fail += 1
    log('fetched %d new symbols, updated %d, %d failed (cache: %d files)' % (got, upd, fail, len(os.listdir(DATA))))


# ---------------- prepare ----------------
def load():
    days = {}                                            # sym -> {date: [(hhmm, o, h, l, c)]}
    for fn in sorted(os.listdir(DATA)):
        sym = fn[:-5]
        by = collections.defaultdict(list)
        for c in json.load(open(os.path.join(DATA, fn))):
            ts = str(c[0]); d, t = ts[:10], ts[11:16]
            if '09:15' <= t <= '15:15' and None not in c[1:5]:
                by[d].append((t, float(c[1]), float(c[2]), float(c[3]), float(c[4])))
        days[sym] = {d: sorted(v) for d, v in by.items() if len(v) >= 20}
    return days


def ema8(days):
    """8 EMA on 15-min closes, continuous across days. Returns {date: [ema at each candle]}."""
    a, e, out = 2.0 / 9, None, {}
    for d in sorted(days):
        row = []
        for c in days[d]:
            e = c[4] if e is None else a * c[4] + (1 - a) * e
            row.append(e)
        out[d] = row
    return out


# ---------------- simulate ----------------
def trade(cs, em, side, j0, tgt_r):
    """Scan from candle j0 for a breakout candle; entry on next candle breaking it. Returns trade dict or None."""
    orh, orl = cs[0][2], cs[0][3]
    for i in range(j0, len(cs) - 1):
        t, o, h, l, c = cs[i]
        if t > LAST_ENTRY:
            return None
        if side == 1 and not (c > orh and c > o and c > em[i]):
            continue
        if side == -1 and not (c < orl and c < o and c < em[i]):
            continue
        n = cs[i + 1]
        if side == 1 and n[2] > h:
            fill, sl = max(n[1], h), l
        elif side == -1 and n[3] < l:
            fill, sl = min(n[1], l), h
        else:
            continue                                     # agli candle ne break nahi kiya: agla breakout dhoondo
        risk = (fill - sl) * side
        if risk <= 0:
            continue
        tg = fill + side * tgt_r * risk
        ex = why = None
        for k in range(i + 1, len(cs)):
            _, ko, kh, kl, kc = cs[k]
            if k > i + 1 and (ko - sl) * side <= 0:
                ex, why = ko, 'SL(gap)'; break
            if (kl - sl) * side <= 0 if side == 1 else (kh - sl) * side <= 0:
                ex, why = sl, 'SL'; break
            if k == i + 1:
                if (kc - tg) * side >= 0:
                    ex, why = tg, 'TARGET'; break
                continue
            if (kh - tg) * side >= 0 if side == 1 else (kl - tg) * side >= 0:
                ex, why = tg, 'TARGET'; break
        if ex is None:
            ex, why = cs[-1][4], 'EOD'
        return dict(time=cs[i + 1][0], bct=t, fill=fill, sl=sl, exit=ex, why=why, risk=risk, gross=(ex - fill) * side / risk,
                    riskpct=risk / fill * 100)
    return None


def main():
    os.makedirs('out', exist_ok=True)
    try:
        fetch_all()
    except Exception:
        log('FETCH ERROR: ' + traceback.format_exc()[-400:])
    if not os.path.isdir(DATA) or not os.listdir(DATA):
        log('no data'); open('out/orb_summary.txt', 'w').write('\n'.join(LINES) + '\n'); sys.exit(1)
    D = load()
    nifty = D.pop('NIFTY_INDEX', {})
    E = {s: ema8(D[s]) for s in D}
    dates = sorted({d for s in D for d in D[s]})
    log('data: %d stocks, %d days (%s to %s), nifty days %d' % (len(D), len(dates), dates[0], dates[-1], len(nifty)))
    prevc = {s: {} for s in D}
    for s in D:
        ds = sorted(D[s])
        for a, b in zip(ds, ds[1:]):
            prevc[s][b] = D[s][a][-1][4]
    nprev = {}
    nd = sorted(nifty)
    for a, b in zip(nd, nd[1:]):
        nprev[b] = nifty[a][-1][4]
    # breadth: % of F&O stocks above prev close at each candle time
    breadth = collections.defaultdict(lambda: [0, 0])
    for s in D:
        for d, cs in D[s].items():
            pc = prevc[s].get(d)
            if pc:
                for c in cs:
                    b = breadth[(d, c[0])]; b[0] += c[4] > pc; b[1] += 1
    # top 20 gainers / losers at 09:30 (first candle close vs prev close)
    rank, vid = {}, {}
    for d in dates:
        ch = [(D[s][d][0][4] / prevc[s][d] - 1, s) for s in D if d in D[s] and prevc[s].get(d)]
        ch.sort()
        rank[d] = ({s for _, s in ch[-20:]}, {s for _, s in ch[:20]})
        # video (awaaz): 9:25 par gainers me jo ~1.5-2% upar (losers me ~1.5-2% neeche), aise 3-4 stock
        g = sorted([(abs(c - 0.0175), s) for c, s in ch if 0.01 <= c <= 0.025])[:4]
        l_ = sorted([(abs(-c - 0.0175), s) for c, s in ch if -0.025 <= c <= -0.01])[:4]
        up = sum(1 for c, _ in ch if c > 0)
        vid[d] = ({s for _, s in g}, {s for _, s in l_}, up > len(ch) - up)
    half = dates[len(dates) // 2]
    res = collections.defaultdict(list)
    main_trades = []
    for s in D:
        for d, cs in D[s].items():
            pc = prevc[s].get(d)
            if not pc or d not in rank:
                continue
            for side in (1, -1):
                top = s in (rank[d][0] if side == 1 else rank[d][1])
                vsel = s in (vid[d][0] if side == 1 else vid[d][1])
                for tr_ in TARGETS:
                    t = trade(cs, E[s][d], side, 1, tr_)
                    if not t:
                        continue
                    bt = breadth.get((d, t['bct']), [0, 1])
                    br = bt[0] / max(bt[1], 1)
                    nl = [c[4] for c in nifty.get(d, []) if c[0] <= t['bct']]
                    ngreen = (nl[-1] > nprev[d]) if nl and d in nprev else None
                    mk = {'NONE': True, 'NIFTY': ngreen is not None and ngreen == (side == 1),
                          'BREADTH': (br > 0.5) == (side == 1)}
                    mk['NIFTY+BREADTH'] = mk['NIFTY'] and mk['BREADTH']
                    mk['AD930'] = vid[d][2] == (side == 1)          # video: 9:25 advance/decline se disha
                    for m, ok in mk.items():
                        if not ok:
                            continue
                        for sel in ('ALL_FNO', 'TOP20', 'VIDEO'):
                            if sel == 'TOP20' and not top:
                                continue
                            if sel == 'VIDEO' and not vsel:
                                continue
                            for cost in COSTS:
                                net = t['gross'] - cost * t['fill'] / t['risk']
                                res[('LONG' if side == 1 else 'SHORT', sel, m, tr_, cost)].append((d, net, t['riskpct'], t['why']))
                    if tr_ == 2.0 and mk['NIFTY+BREADTH'] and top:
                        main_trades.append(dict(date=d, symbol=s, side='LONG' if side == 1 else 'SHORT', entry_time=t['time'],
                                                fill=round(t['fill'], 2), sl=round(t['sl'], 2), exit=round(t['exit'], 2),
                                                why=t['why'], risk_pct=round(t['riskpct'], 2),
                                                R_net=round(t['gross'] - COSTS[-1] * t['fill'] / t['risk'], 3)))

    def st(L):
        n = len(L)
        if not n:
            return None
        r = [x[1] for x in L]
        gp, gl = sum(x for x in r if x > 0), -sum(x for x in r if x < 0)
        h1 = [x[1] for x in L if x[0] < half]; h2 = [x[1] for x in L if x[0] >= half]
        why = collections.Counter(x[3] for x in L)
        return dict(n=n, win=round(100.0 * sum(1 for x in r if x > 0) / n), avgR=sum(r) / n, pf=(gp / gl) if gl else 0,
                    h1=(sum(h1) / len(h1)) if h1 else 0, h2=(sum(h2) / len(h2)) if h2 else 0,
                    risk=sum(x[2] for x in L) / n, tgt=round(100.0 * why['TARGET'] / n), perday=n / len(dates))
    rows = []
    for k, L in res.items():
        s_ = st(L)
        if s_:
            rows.append(dict(side=k[0], select=k[1], market=k[2], target=k[3], cost_pct=k[4] * 100, **s_))
    with open('out/orb_results.csv', 'w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open('out/orb_trades.csv', 'w', newline='') as h:
        if main_trades:
            w = csv.DictWriter(h, fieldnames=list(main_trades[0].keys())); w.writeheader(); w.writerows(main_trades)
    log('')
    log('ORB 15-min + 8 EMA STUDY (generated %s). Half split at %s (H1 = pehle, H2 = baad).' % (datetime.date.today(), half))
    log('R = profit / risk (risk = entry se SL). Cost 0.15%% round trip = brokerage + STT + charges + slippage, R me badla gaya.')
    log('win = %% trades profit me, tgt = %% trades target tak gaye, risk%% = avg SL doori, trades/day = poore F&O me roz kitne.')
    for cost in COSTS:
        log('')
        log('== %s ==' % ('COST 0 (sirf edge, charges se pehle)' if cost == 0 else 'COST 0.15% (asli jaisa)'))
        log('%-5s %-7s %-13s %4s %6s %4s %4s %7s %5s %7s %7s %6s %8s' % ('side', 'select', 'market', 'tgt', 'n', 'win', 'tgt%', 'avgR', 'PF', 'H1', 'H2', 'risk%', 'trd/day'))
        for r in sorted([r for r in rows if r['cost_pct'] == cost * 100], key=lambda r: (r['side'], r['select'], r['market'], r['target'])):
            log('%-5s %-7s %-13s %4.1f %6d %3d%% %3d%% %7.3f %5.2f %7.3f %7.3f %5.2f%% %8.1f' % (
                r['side'], r['select'], r['market'], r['target'], r['n'], r['win'], r['tgt'], r['avgR'], r['pf'], r['h1'], r['h2'], r['risk'], r['perday']))
    good = [r for r in rows if r['cost_pct'] > 0 and r['avgR'] > 0 and r['h1'] > 0 and r['h2'] > 0 and r['n'] >= 200]
    log('')
    log('Cost ke baad dono halves me plus (n>=200): %d of %d combos.' % (len(good), len([r for r in rows if r['cost_pct'] > 0])))
    for r in sorted(good, key=lambda r: -r['avgR'])[:10]:
        log('  %s %s %s tgt %.1f: n %d, avgR %.3f, H1 %.3f, H2 %.3f' % (r['side'], r['select'], r['market'], r['target'], r['n'], r['avgR'], r['h1'], r['h2']))
    log('Video (awaaz) wala asli setup = VIDEO select (9:30 par 1-2.5% upar/neeche, 3-4 stock) + AD930 (advance/decline), target 3R.')
    log('PDF wala = TOP20 + NIFTY+BREADTH, target 1.5-2R. Sector filter data me nahi hai.')
    log('Bahut saare combos dekhe: chhota plus luck ho sakta hai. Past results do not guarantee future results.')
    open('out/orb_summary.txt', 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
