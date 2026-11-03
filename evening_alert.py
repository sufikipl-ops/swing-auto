# Roz shaam (dip scan + paper ke baad) Telegram: "KAL KE TRADE". User din me max 2 trade leta hai, isliye app khud 2 chunta hai:
# jo setup app "trade karo" (paper.py go=True) keh raha hai, unme se sabse zyada liquid 2 (pick_study: chunne ka tareeka fark nahi
# karta, liquid me entry/exit aasaan). Koi go signal nahi -> "kal trade nahi" + wajah. Din me ek hi baar (paper.json 'alert_sent').
# usage: python evening_alert.py
import csv, json, os, sys
import live

RISK = float(os.environ.get('ALERT_RISK', '500'))
NAMES = {'A': 'Dip A', 'B': 'Dip B', 'BOUNCE': 'Oversold bounce', 'DEEP': 'Gehra oversold', 'STRUCT': 'Structure',
         'STRUCT_DEEP': 'Structure (gehra)', 'DROP10': 'Ek din me 10% gira', 'NEWDROP': 'Naye listing ka dip',
         'BREAKOUT': 'Breakout', 'PULLBACK': 'Pullback'}
# sirf 4 saal ke test me pass setup (breakout/pullback experimental, result wale sirf dekhne ke liye)
TESTED = ('A', 'BOUNCE', 'DEEP', 'STRUCT', 'STRUCT_DEEP', 'DROP10', 'NEWDROP')
HOLD = {'STRUCT': 10, 'STRUCT_DEEP': 10, 'DROP10': 3}
# 4 saal (pick_study, VWEAK, close-par SL) me jeet %: is kram me pehle -> roz sirf 1 "sabse solid" trade
WIN = {'DROP10': 79, 'BOUNCE': 67, 'DEEP': 64, 'STRUCT_DEEP': 64, 'NEWDROP': 54, 'A': 54, 'STRUCT': 52}
MAXPICK = int(os.environ.get('ALERT_MAX', '1'))


def main():
    led = json.load(open('docs/paper.json', encoding='utf-8'))
    reg = json.load(open('docs/regime_today.json'))
    day = reg.get('date')
    if led.get('alert_sent') == day:
        print('alert already sent for', day); return
    turn = {}
    for fn, key in (('docs/dip_latest.csv', 'TIER'), ('docs/screen_latest.csv', 'SETUP')):
        if os.path.exists(fn):
            for r in csv.DictReader(open(fn, encoding='utf-8')):
                try:
                    turn[(r.get('SYMBOL'), r.get(key))] = float(r.get('TURN20_CR') or 0)
                except ValueError:
                    pass
    go = [s for s in led['signals'] if s.get('sig') == day and s.get('go') and s.get('status') == 'WAIT' and s['setup'] in TESTED]
    best = {}
    for s in go:
        if s['sym'] not in best or turn.get((s['sym'], s['setup']), 0) > turn.get((best[s['sym']]['sym'], best[s['sym']]['setup']), 0):
            best[s['sym']] = s
    try:
        SH = json.load(open('docs/stock_hist.json')).get('data', {})
    except Exception:
        SH = {}
    HK = {'A': 'DIP_A', 'BOUNCE': 'OVERSOLD_BOUNCE', 'DEEP': 'DEEP_OVERSOLD', 'STRUCT': 'STRUCT_ALL', 'STRUCT_DEEP': 'STRUCT_ALL'}

    def own(s):                                  # is stock par is setup ka apna record (Time Machine): 5+ baar aur minus = peeche
        h = ((SH.get(s['sym']) or {}).get(HK.get(s['setup'], '')) or {}).get('ALL')
        return h if h and h[0] >= 5 else None

    def rank(s):
        h = own(s)
        return (-(WIN.get(s['setup'], 0) - (15 if h and h[2] < 0 else 0)), -turn.get((s['sym'], s['setup']), 0))
    pick = sorted(best.values(), key=rank)[:MAXPICK]
    dayn = max([s.get('dayn', 0) for s in go] + [0])
    L = ['KAL KE TRADE (%s ka scan)' % day,
         'Market: %s%% stock EMA50 ke upar -> %s' % (reg.get('breadth'), reg.get('regime'))]
    if not pick:
        why = ('Market bahut kamzor par aaj sirf %d stock me signal (16 se kam = chhota din)' % dayn if reg.get('regime') == 'VWEAK'
               else 'Aaj koi tested setup nahi bana')
        L += ['', 'KAL TRADE NAHI. ' + why + '. Paisa bachao.']
    else:
        if dayn >= 16: L.append('BADA DIN: %d liquid stock ek saath oversold' % dayn)
        L.append('')
        for k, s in enumerate(pick, 1):
            c, atr = s['close'], s['atr']
            stop = s.get('stop_ref') or round(c - 2 * atr, 2)
            risk = max(c - stop, 0.01); qty = int(min(RISK // risk, 50000 // c))
            tgt = s.get('mean') if s['setup'] == 'DROP10' else (round(c + 2 * risk, 2) if s['setup'].startswith('STRUCT') else None)
            h = own(s)
            L.append('%d) %s - %s' % (k, s['sym'], NAMES.get(s['setup'], s['setup'])))
            L.append('   Kyun ye: is setup ki 4 saal me jeet ~%d%% (sabse zyada aaj ke signals me)%s' % (WIN.get(s['setup'], 0),
                     ('; is stock par pehle %d baar, %d jeete' % (h[0], h[1])) if h else ''))
            L.append('   Kal 9:20 par kharido (aaj ka close %.2f; kal open isse +1.5%% upar ya -3%% neeche ho to SKIP)' % c)
            L.append('   SL %.2f (3:15 par close iske neeche ho tabhi becho) | Qty %d (risk ~Rs%d)' % (stop, qty, round(qty * risk)))
            L.append('   ' + ('Target %.2f, ' % tgt if tgt else '') + 'max %d din, phir close par bahar' % HOLD.get(s['setup'], 5))
        L += ['', 'Aaj ka 1 sabse solid trade. Baaki %d signal app ke Setups tab me (lena zaroori nahi).' % max(0, len(best) - len(pick))]
    text = '\n'.join(L)
    print(text)
    url, pkey = live.page_config()
    url = os.environ.get('PIN_URL', url); pkey = os.environ.get('PIN_KEY', pkey)
    if not url:
        print('PIN_URL nahi'); return
    ok, why = live.notify(url, pkey, text)
    print('notify', ok, why)
    if ok:
        led['alert_sent'] = day
        json.dump(led, open('docs/paper.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
