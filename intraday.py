# App chart ke 15-min / 1-ghanta timeframe: candles.json wale stocks ke pichhle ~5 trading din ke 15-min candles
# (Angel One getCandleData) -> docs/intraday.json. Roz shaam app.yml me chalta hai. Secrets sirf GitHub Secrets me.
# usage: python intraday.py
import os, sys, json, time, datetime

import live

DAYS = int(os.environ.get('INTRA_DAYS', '8'))     # calendar din peeche (~5 trading din)


def main():
    key = os.environ.get('ANGEL_API_KEY', '').strip(); cid = os.environ.get('ANGEL_CLIENT_ID', '').strip()
    pin = os.environ.get('ANGEL_PIN', '').strip(); tsec = os.environ.get('ANGEL_TOTP_SECRET', '').strip()
    if not (key and cid and pin and tsec):
        print('Angel secrets missing, skip'); return
    try:
        syms = list(json.load(open('docs/candles.json')).get('s', {}))
    except Exception:
        print('candles.json nahi mila, skip'); return
    jwt = live.login(key, cid, pin, tsec)
    master = None
    for attempt in range(4):
        master = live.http_json(live.MASTER, None, {}, timeout=180)
        if isinstance(master, list) and len(master) > 1000:
            break
        time.sleep(10 * (attempt + 1))
    if not isinstance(master, list):
        print('master download fail'); return
    tok = {m['symbol'][:-3]: m['token'] for m in master if m.get('exch_seg') == 'NSE' and str(m.get('symbol', '')).endswith('-EQ')}
    now = live.ist_now(); fr = (now - datetime.timedelta(days=DAYS)).strftime('%Y-%m-%d') + ' 09:15'
    to = now.strftime('%Y-%m-%d %H:%M')
    out, fail = {}, 0
    for s in syms:
        if s not in tok: continue
        rows = None
        for attempt in range(3):
            r = live.angel(key, '/rest/secure/angelbroking/historical/v1/getCandleData',
                           {'exchange': 'NSE', 'symboltoken': tok[s], 'interval': 'FIFTEEN_MINUTE', 'fromdate': fr, 'todate': to}, jwt)
            if r.get('status'):
                rows = r.get('data') or []; break
            time.sleep(2 + 3 * attempt)
        if rows:
            out[s] = [[str(c[0])[:16].replace('T', ' '), round(float(c[1]), 2), round(float(c[2]), 2), round(float(c[3]), 2),
                       round(float(c[4]), 2), int(c[5] or 0)] for c in rows if None not in c[1:5]]
        else:
            fail += 1
        time.sleep(0.4)
    json.dump({'updated': now.strftime('%Y-%m-%d %H:%M IST'), 'tf': '15m', 's': out}, open('docs/intraday.json', 'w'), separators=(',', ':'))
    print('intraday.json: %d stocks, %d fail, %d bytes' % (len(out), fail, os.path.getsize('docs/intraday.json')))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('intraday error:', str(e)[:200])
