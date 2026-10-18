# App ke stock page ka chart: kaam ke stocks (picks, dip/bounce/structure, locked, trades) ke pichhle ~100 din ke
# daily candles -> docs/candles.json. Saare 2600+ stock nahi (roz ka file bahut bada ho jaata); baaki ke liye app
# TradingView ka link dikhata hai.
# usage: python candles.py <bhav_folder>   (app.yml, stock_report.py ke baad)
import csv, glob, os, sys, json, datetime

DAYS = int(os.environ.get('CANDLE_DAYS', '100'))
MAXSYM = int(os.environ.get('CANDLE_MAXSYM', '160'))


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


def wanted():
    syms = []
    def add(s):
        s = (s or '').strip().upper()
        if s and s not in syms:
            syms.append(s)
    for fn, col in (('screen_latest.csv', 'SYMBOL'), ('dip_latest.csv', 'SYMBOL'), ('picks_review.csv', 'symbol')):
        for d in ('docs', 'out'):
            p = os.path.join(d, fn)
            if os.path.exists(p):
                for r in csv.DictReader(open(p, encoding='utf-8')):
                    add(r.get(col))
                break
    try:                                             # locked (Pins) + Picks sheet ke trades
        import live
        url, key = live.page_config()
        st = live.server_state(url, key) if url.startswith('https://') else None
        for s in (st or {}).get('pins') or []:
            add(s)
        for s in live.sheet_trade_symbols(live.page_var('PICKS_GVIZ')):
            add(s)
    except Exception as e:
        print('pins/sheet skip:', str(e)[:100])
    return syms[:MAXSYM]


def main():
    bhav = sys.argv[1] if len(sys.argv) > 1 else 'data'
    syms = set(wanted())
    files = sorted(glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')),
                   key=lambda f: datetime.datetime.strptime(os.path.basename(f)[-12:-4], '%d%m%Y'))[-DAYS:]
    dates, rows = [], {s: {} for s in syms}
    for f in files:
        d = None
        with open(f, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[1].strip() != 'EQ': continue
                s = r[0].strip()
                if s not in syms: continue
                t = [num(r[k]) for k in (4, 5, 6, 8, 10)]
                if None in t: continue
                d = d or datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date().isoformat()
                rows[s][d] = [round(t[0], 2), round(t[1], 2), round(t[2], 2), round(t[3], 2), int(t[4])]
        if d: dates.append(d)
    out = {}
    for s, byd in rows.items():
        if len(byd) >= 20:
            out[s] = [[i] + byd[d] for i, d in enumerate(dates) if d in byd]     # [date_index, o, h, l, c, vol]
    os.makedirs('docs', exist_ok=True)
    json.dump({'updated': datetime.date.today().isoformat(), 'dates': dates, 's': out},
              open('docs/candles.json', 'w'), separators=(',', ':'))
    print('candles.json: %d stocks x %d days, %d bytes' % (len(out), len(dates), os.path.getsize('docs/candles.json')))


if __name__ == '__main__':
    main()
