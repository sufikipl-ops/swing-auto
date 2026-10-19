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
         'STRUCT': (10, 2.0, 'Structure'), 'STRUCT_DEEP': (10, 2.0, 'Structure (gehra)'), 'NEWDROP': (5, None, 'Naye listing ka dip'),
         'BREAKOUT': (5, 'atr', 'Pick: breakout'), 'PULLBACK': (5, 'atr', 'Pick: pullback')}


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
            if st in ('BREAKOUT', 'PULLBACK'):
                s['trig'] = num(r.get('ENTRY')) or c
                lo5 = num(r.get('LOW5'))
                s['stop_ref'] = (lo5 - 0.1 * atr) if lo5 else None
            out.append(s); have.add((sym, st, d))
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
    if not days:
        return
    maxd, tgt, _ = RULES[s['setup']]
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
    tp = e + tgt * risk if isinstance(tgt, float) else (e + min(1.5 * s['atr'], 2 * risk) if tgt == 'atr' else None)
    qty = int(min(RISK // risk, CAP // e))
    if qty < 1:
        s.update(status='SKIP', why='Capital/risk me 1 share bhi nahi', exit_date=d0); return
    s.update(entry_date=d0, entry=round(e, 2), stop=round(stop, 2), target=round(tp, 2) if tp else None, qty=qty)
    for k, d in enumerate(days[:maxd]):
        o, h, l, c = p[d]
        if l <= stop:
            ex = stop if k == 0 else min(o, stop)
            return close_it(s, d, ex, 'SL', e, risk, qty)
        if tp and h >= tp:
            return close_it(s, d, max(o, tp) if k > 0 else tp, 'Target', e, risk, qty)
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
    todo = [s for s in led['signals'] if s['status'] not in ('CLOSED', 'SKIP')]
    px = load_px(bhav, set(s['sym'] for s in todo))
    for s in todo:
        run(s, px.get(s['sym'], {}))
    st = collections.defaultdict(lambda: dict(n=0, win=0, R=0.0, pnl=0, open=0, skip=0))
    for s in led['signals']:
        for k in (s['setup'], 'ALL'):
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
