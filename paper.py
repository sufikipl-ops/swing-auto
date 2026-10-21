# Paper trading: app ka har signal nakli paise se track (asli paisa nahi). Roz shaam dip scan ke baad chalta hai.
# Signal (aaj ke close par) -> kal OPEN par entry (gap rule: open close se +1.5% upar / -3% neeche = SKIP) -> SL / target /
# max din par bahar. Same din SL aur target dono = SL (bura maan ke). Kharcha 0.25%. Risk har trade ₹RISK.
# "go" = us din app ne ye setup trade karne ko kaha tha (market haal ke hisaab se) ya sirf dikhaya tha.
# usage: python paper.py <bhav_folder>   -> docs/paper.json
import os, sys, csv, json, glob, datetime, collections

OUT = 'docs/paper.json'
RISK = float(os.environ.get('PAPER_RISK', '500'))
CAP = float(os.environ.get('PAPER_CAP', '50000'))       # ek trade me itne se zyada paisa nahi
COST = 0.0025
GAP_UP, GAP_DN = 1.015, 0.97
# setup -> (max din, target R ya None, naam)
RULES = {'A': (5, None, 'Dip A'), 'B': (5, None, 'Dip B'), 'BOUNCE': (5, None, 'Oversold bounce'), 'DEEP': (5, None, 'Gehra oversold'),
         'STRUCT': (10, 2.0, 'Structure'), 'STRUCT_DEEP': (10, 2.0, 'Structure (gehra)'), 'NEWDROP': (5, None, 'Naye listing ka dip'), 'DROP10': (3, 'mean', 'Ek din me 10% gira'),
         'BREAKOUT': (5, 'atr', 'Pick: breakout'), 'PULLBACK': (5, 'atr', 'Pick: pullback'),
         'RES_GAP': (20, None, 'Result: gap-up tika (dekhne ke liye)'), 'RES_UP8': (20, None, 'Result: +8% vol 3x (dekhne ke liye)')}
# sirf dekhne wale (results_study me tentative plus, 2 saal data): result wale din CLOSE par entry, 20 din, SL 2 ATR. App inhe trade
# karne ko nahi kehta (go=False) aur ye kul (ALL) hisaab me nahi gine jaate.
WATCH = ('RES_GAP', 'RES_UP8')


def num(x):
    try:
        return float(str(x).strip())
    except (ValueError, TypeError):
        return None


def go_flag(setup, regime, note=''):
    """App us din kya kehta: trade karo (True) ya sirf dikhaya / 'aaj trade nahi' (False). index.html ke sections jaisa."""
    if setup in ('A',):
        return True
    if setup == 'B':
        return regime in ('STRONG', 'MIXED')
    if setup in ('BOUNCE', 'DEEP', 'STRUCT', 'STRUCT_DEEP'):
        return regime == 'VWEAK'
    if setup == 'DROP10':
        return regime == 'VWEAK'
    if setup == 'NEWDROP':
        return regime != 'MIXED'
    if setup in ('BREAKOUT', 'PULLBACK'):
        return 'EXTENDED' not in note and 'LOW_DELIV' not in note
    return False


def new_signals(led):
    have = set((s['sym'], s['setup'], s['sig']) for s in led['signals'])
    try:
        reg = json.load(open('docs/regime_today.json'))
    except Exception:
        reg = {}
    out = []
    for fn, key in (('docs/dip_latest.csv', 'TIER'), ('docs/screen_latest.csv', 'SETUP')):
        if not os.path.exists(fn):
            continue
        for r in csv.DictReader(open(fn, encoding='utf-8')):
            st, sym, d = (r.get(key) or '').strip(), (r.get('SYMBOL') or '').strip(), (r.get('DATE') or '').strip()
            if st not in RULES or not sym or not d or (sym, st, d) in have:
                continue
            c, atr = num(r.get('CLOSE')), num(r.get('ATR14'))
            if not c or not atr:
                continue
            rg = reg.get('regime') if reg.get('date') == d else None
            s = dict(sym=sym, setup=st, sig=d, close=c, atr=atr, regime=rg, go=go_flag(st, rg, r.get('NOTE') or ''), status='WAIT')
            if st in ('STRUCT', 'STRUCT_DEEP'):
                s['stop_ref'] = num(r.get('STOP_REF'))
            if st == 'DROP10':
                s['mean'] = num(r.get('TARGET_REF'))       # 20-din average: wahan becho
            if st in ('BREAKOUT', 'PULLBACK'):
                s['trig'] = num(r.get('ENTRY')) or c
                lo5 = num(r.get('LOW5'))
                s['stop_ref'] = (lo5 - 0.1 * atr) if lo5 else None
            out.append(s); have.add((sym, st, d))
    return out


def result_signals(led, bhav):
    """Aaj jin companies ka result ka reaction din tha (NSE 'Outcome of Board Meeting', results_study jaisa niyam):
    RES_GAP = gap 3%+ aur din bhar tika (close>=open), volume 2x+; RES_UP8 = din +8%+, volume 3x+. Liquid (20-din 5 cr+)."""
    files = {}                                             # tareekh file ke andar se (chhutti wali file me pichhla din hota hai)
    for f in glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')):
        try:
            with open(f, newline='', encoding='utf-8', errors='ignore') as h:
                rd = csv.reader(h); next(rd, None); r = next(rd, None)
            files[datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()] = f
        except (ValueError, TypeError, IndexError, StopIteration):
            pass
    tdays = sorted(files)[-26:]
    if len(tdays) < 22:
        return []
    D = tdays[-1]
    try:
        from results_study import nse
        got = nse('https://www.nseindia.com/api/corporate-announcements?index=equities&from_date=%s&to_date=%s'
                  % ((D - datetime.timedelta(days=6)).strftime('%d-%m-%Y'), D.strftime('%d-%m-%Y')))
    except Exception as e:
        print('paper: NSE results fetch fail', str(e)[:80]); return []
    ev = set()
    for r in got:
        tx = (r.get('attchmntText') or '').lower()
        if (r.get('desc') or '') != 'Outcome of Board Meeting' or 'result' not in tx or ('financial' not in tx and 'quarter' not in tx):
            continue
        try:
            dt = datetime.datetime.strptime((r.get('sort_date') or '')[:16], '%Y-%m-%d %H:%M')
        except ValueError:
            continue
        rd_ = dt.date() if dt.hour * 60 + dt.minute < 9 * 60 + 15 else dt.date() + datetime.timedelta(days=1)
        if next((d for d in tdays if d >= rd_), None) == D:
            ev.add((r.get('symbol') or '').strip())
    ev.discard('')
    px = collections.defaultdict(dict)
    for d in tdays:
        with open(files[d], newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[0].strip() not in ev or r[1].strip() != 'EQ':
                    continue
                try:
                    px[r[0].strip()][d] = (float(r[4]), float(r[5]), float(r[6]), float(r[8]), float(r[10]), float(r[11]) / 100.0)
                except ValueError:
                    pass
    try:
        reg = json.load(open('docs/regime_today.json'))
    except Exception:
        reg = {}
    rg = reg.get('regime') if reg.get('date') == D.isoformat() else None
    have = set((s['sym'], s['setup'], s['sig']) for s in led['signals']); out = []
    for sym in sorted(ev):
        b = [px[sym][d] for d in tdays if d in px[sym]]
        if len(b) < 22 or D not in px[sym]:
            continue
        b = b[-22:]; o, h, l, c, v = b[-1][:5]; pc = b[-2][3]
        if sum(x[5] for x in b[-21:-1]) / 20.0 < 5:
            continue
        vx = v / (sum(x[4] for x in b[-21:-1]) / 20.0); gap = (o / pc - 1) * 100; day = (c / pc - 1) * 100
        tr = [max(b[k][1] - b[k][2], abs(b[k][1] - b[k - 1][3]), abs(b[k][2] - b[k - 1][3])) for k in range(len(b) - 14, len(b))]
        atr = sum(tr) / 14.0
        for st, ok in (('RES_GAP', gap >= 3 and c >= o and vx >= 2), ('RES_UP8', day >= 8 and vx >= 3)):
            if not ok or (sym, st, D.isoformat()) in have:
                continue
            out.append(dict(sym=sym, setup=st, sig=D.isoformat(), close=c, atr=round(atr, 2), regime=rg, go=False, status='WAIT',
                            at_close=True, note='gap %+.1f%%, din %+.1f%%, vol %.1fx' % (gap, day, vx)))
    print('paper: aaj %d result reaction, %d result signal' % (len(ev), len(out)))
    return out


def load_px(bhav, syms):
    px = collections.defaultdict(dict)
    for f in glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')):
        with open(f, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[0].strip() not in syms or r[1].strip() not in ('EQ', 'BE'):
                    continue
                try:
                    d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date().isoformat()
                    px[r[0].strip()][d] = (float(r[4]), float(r[5]), float(r[6]), float(r[8]))
                except ValueError:
                    continue
    return px


def run(s, p):
    """Ek signal ko shuru se aaj tak chalao (data jitna hai). Band (CLOSED/SKIP) ho chuka to haath nahi lagate."""
    if s['status'] in ('CLOSED', 'SKIP'):
        return
    days = sorted(d for d in p if d > s['sig'])
    maxd, tgt, _ = RULES[s['setup']]
    if s.get('at_close'):                                  # result wala: usi din close par liya (3:15 jaisa), gap rule nahi
        e = s['close']; stop = e - 2 * s['atr']; risk = e - stop; qty = int(min(RISK // risk, CAP // e))
        if qty < 1:
            s.update(status='SKIP', why='Capital/risk me 1 share bhi nahi', exit_date=s['sig']); return
        s.update(entry_date=s['sig'], entry=round(e, 2), stop=round(stop, 2), target=None, qty=qty)
        if not days:
            s.update(status='OPEN', last=round(e, 2), last_date=s['sig'], held=0, R=round(-COST * e / risk, 2), pnl=round(-COST * qty * e))
            return
        return walk(s, p, days, maxd, e, stop, None, risk, qty)
    if not days:
        return
    d0 = days[0]; o, h, l, c = p[d0]
    if o > s['close'] * GAP_UP or o < s['close'] * GAP_DN:
        s.update(status='SKIP', why='Gap (open %.2f, kal close %.2f)' % (o, s['close']), exit_date=d0); return
    if s['setup'] in ('BREAKOUT', 'PULLBACK'):
        if h < s['trig']:
            s.update(status='SKIP', why='Trigger %.2f tak nahi gaya' % s['trig'], exit_date=d0); return
        e = max(o, s['trig'])
    else:
        e = o
    if s['setup'] in ('STRUCT', 'STRUCT_DEEP', 'BREAKOUT', 'PULLBACK') and s.get('stop_ref'):
        stop = s['stop_ref']
        if s['setup'] in ('BREAKOUT', 'PULLBACK'):
            stop = max(stop, e - 2 * s['atr'])
    else:
        stop = e - 2 * s['atr']
    risk = e - stop
    if risk <= 0 or risk / e > 0.15:
        s.update(status='SKIP', why='SL entry ke upar ya 15%% se door', exit_date=d0); return
    tp = e + tgt * risk if isinstance(tgt, float) else (e + min(1.5 * s['atr'], 2 * risk) if tgt == 'atr' else
                                                       (s['mean'] if tgt == 'mean' and s.get('mean') and s['mean'] > e else None))
    qty = int(min(RISK // risk, CAP // e))
    if qty < 1:
        s.update(status='SKIP', why='Capital/risk me 1 share bhi nahi', exit_date=d0); return
    s.update(entry_date=d0, entry=round(e, 2), stop=round(stop, 2), target=round(tp, 2) if tp else None, qty=qty)
    return walk(s, p, days, maxd, e, stop, tp, risk, qty, True)


def walk(s, p, days, maxd, e, stop, tp, risk, qty, open_day=False):
    """open_day: pehla din entry ka din hai (open par liya) -> us din SL lage to SL bhav, warna gap me open bhav."""
    for k, d in enumerate(days[:maxd]):
        o, h, l, c = p[d]
        if l <= stop:
            ex = stop if (k == 0 and open_day) else min(o, stop)
            return close_it(s, d, ex, 'SL', e, risk, qty)
        if tp and h >= tp:
            return close_it(s, d, tp if (k == 0 and open_day) else max(o, tp), 'Target', e, risk, qty)
        if k == maxd - 1:
            return close_it(s, d, c, '%d din poore' % maxd, e, risk, qty)
    d = days[min(len(days), maxd) - 1]; c = p[d][3]
    s.update(status='OPEN', last=round(c, 2), last_date=d, held=min(len(days), maxd),
             R=round((c - e) / risk - COST * e / risk, 2), pnl=round(qty * (c - e) - COST * qty * e))


def close_it(s, d, ex, why, e, risk, qty):
    s.update(status='CLOSED', exit_date=d, exit=round(ex, 2), why=why, R=round((ex - e) / risk - COST * e / risk, 2),
             pnl=round(qty * (ex - e) - COST * qty * e))


def main():
    bhav = sys.argv[1] if len(sys.argv) > 1 else 'data'
    try:
        led = json.load(open(OUT, encoding='utf-8'))
    except Exception:
        led = {'start': datetime.date.today().isoformat(), 'risk': RISK, 'signals': []}
    led['signals'] += new_signals(led)
    led['signals'] += result_signals(led, bhav)
    todo = [s for s in led['signals'] if s['status'] not in ('CLOSED', 'SKIP')]
    px = load_px(bhav, set(s['sym'] for s in todo))
    for s in todo:
        run(s, px.get(s['sym'], {}))
    st = collections.defaultdict(lambda: dict(n=0, win=0, R=0.0, pnl=0, open=0, skip=0))
    for s in led['signals']:
        for k in ((s['setup'],) if s['setup'] in WATCH else (s['setup'], 'ALL')):
            for g in (('go' if s.get('go') else 'show'), 'all'):
                x = st[k + '|' + g]
                if s['status'] == 'CLOSED':
                    x['n'] += 1; x['win'] += s['R'] > 0; x['R'] += s['R']; x['pnl'] += s['pnl']
                elif s['status'] == 'OPEN':
                    x['open'] += 1
                elif s['status'] == 'SKIP':
                    x['skip'] += 1
    for x in st.values():
        x['R'] = round(x['R'], 2)
    led.update(updated=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), stats=st,
               names={k: v[2] for k, v in RULES.items()})
    json.dump(led, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    c = collections.Counter(s['status'] for s in led['signals'])
    print('paper: %d signals | %s | band trade %d, kul %+.2fR, ₹%d' % (len(led['signals']), dict(c), st['ALL|all']['n'], st['ALL|all']['R'], st['ALL|all']['pnl']))


if __name__ == '__main__':
    main()
