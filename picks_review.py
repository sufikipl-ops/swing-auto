# Forward test: reviews every pick logged in the Picks tab against real daily prices (bhavcopy). Read-only.
# usage: python picks_review.py <bhav_folder> <output_folder>
# Writes out/picks_review.csv and out/picks_review.txt. Does not touch the Sheet.
import csv, glob, os, sys, io, datetime, collections, urllib.request

bhav_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
SHEET = 'https://docs.google.com/spreadsheets/d/1KNw0jZTk29jwo2ohxdYl11CNxXAvOTcE4Y4lG1Vromw/gviz/tq?tqx=out:csv&gid=777001'
COST_PCT = 0.25
GAP_SKIP = 1.015
TRIGGER_DAYS = 4          # GTT stays alive this many trading days (pick day + 3)
MAX_HOLD = 5              # time-stop: exit at close of this holding day if neither stop nor target hit


def num(x):
    try:
        return float(str(x).replace(',', '').strip())
    except ValueError:
        return None


def pdate(x):
    x = str(x).strip()
    n = num(x)
    if n is not None and n > 40000:
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(n))
    for f in ('%d-%b-%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(x, f).date()
        except ValueError:
            continue
    return None


def load_picks():
    if os.environ.get('PICKS_FILE'):
        raw = open(os.environ['PICKS_FILE'], encoding='utf-8').read()
    else:
        raw = urllib.request.urlopen(SHEET, timeout=60).read().decode('utf-8')
    picks = []
    for r in csv.reader(io.StringIO(raw)):
        if len(r) < 6:
            continue
        d, sym = pdate(r[0]), r[1].strip()
        entry, sl, tgt, qty = num(r[2]), num(r[3]), num(r[4]), num(r[5])
        if d is None or not sym or None in (entry, sl, tgt, qty):
            continue
        picks.append(dict(date=d, symbol=sym, entry=entry, sl=sl, target=tgt, qty=int(qty),
                          reason=(r[6].strip() if len(r) > 6 else '')))
    return picks


def load_prices(symbols):
    px = collections.defaultdict(dict)
    for f in glob.glob(os.path.join(bhav_dir, 'sec_bhavdata_full_*.csv')):
        with open(f, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h)
            next(rd, None)
            for r in rd:
                if len(r) < 15:
                    continue
                r = [c.strip() for c in r]
                if r[1] != 'EQ' or r[0] not in symbols:
                    continue
                try:
                    d = datetime.datetime.strptime(r[2], '%d-%b-%Y').date()
                except ValueError:
                    continue
                px[r[0]][d] = (num(r[4]), num(r[5]), num(r[6]), num(r[8]))
    return px


def review(p, bars):
    """bars: sorted list of (date, open, high, low, close). Returns dict with status, exit, R, pnl."""
    days = [b for b in bars if b[0] >= p['date']]
    out = dict(status='NO_DATA', entry_date='', fill='', exit_date='', exit='', reason_exit='', R='', pnl='')
    if not days:
        return out
    fill, j = None, None
    for k, b in enumerate(days[:TRIGGER_DAYS]):
        if None in b[1:]:
            continue
        if b[2] >= p['entry']:
            if b[1] > p['entry'] * GAP_SKIP:
                out['status'] = 'SKIPPED_GAPUP'
                return out
            fill, j = max(b[1], p['entry']), k
            break
    if fill is None:
        out['status'] = 'NO_TRIGGER' if len(days) >= TRIGGER_DAYS else 'PENDING_TRIGGER'
        return out
    risk = fill - p['sl']
    if risk <= 0:
        out['status'] = 'BAD_LEVELS'
        return out
    out.update(entry_date=days[j][0].isoformat(), fill=round(fill, 2))
    ex, why, exd = None, '', None
    held = 0
    for k in range(j, len(days)):
        d, o, h_, l, c = days[k]
        if None in (o, h_, l, c):
            continue
        held += 1
        if k > j and o <= p['sl']:
            ex, why, exd = o, 'STOP(gap)', d
            break
        if l <= p['sl']:
            ex, why, exd = p['sl'], 'STOP', d
            break
        if h_ >= p['target']:
            ex, why, exd = p['target'], 'TARGET', d
            break
        if held >= MAX_HOLD:
            ex, why, exd = c, 'TIME', d
            break
    if ex is None:
        out['status'] = 'OPEN'
        return out
    cost = COST_PCT / 100.0 * fill
    out.update(status='CLOSED', exit_date=exd.isoformat(), exit=round(ex, 2), reason_exit=why,
               R=round((ex - fill - cost) / risk, 2), pnl=round((ex - fill - cost) * p['qty'], 0))
    return out


def main():
    lines = ['PICKS REVIEW (forward test) %s' % datetime.date.today().isoformat()]
    try:
        picks = load_picks()
    except Exception as e:
        lines.append('FAIL reading Picks sheet: %s' % str(e)[:200])
        open(os.path.join(out_dir, 'picks_review.txt'), 'w').write('\n'.join(lines) + '\n')
        print('\n'.join(lines)); sys.exit(1)
    lines.append('picks read: %d' % len(picks))
    px = load_prices(set(p['symbol'] for p in picks))
    rows = []
    for p in picks:
        bars = sorted((d,) + v for d, v in px.get(p['symbol'], {}).items())
        res = review(p, bars)
        rows.append(dict(date=p['date'].isoformat(), symbol=p['symbol'], entry=p['entry'], sl=p['sl'],
                         target=p['target'], qty=p['qty'], **res))
    cols = ['date', 'symbol', 'entry', 'sl', 'target', 'qty', 'status', 'entry_date', 'fill', 'exit_date', 'exit',
            'reason_exit', 'R', 'pnl']
    with open(os.path.join(out_dir, 'picks_review.csv'), 'w', newline='', encoding='utf-8') as h:
        w = csv.DictWriter(h, fieldnames=cols, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    lines.append('%-10s %-12s %8s %8s %8s %4s %-15s %-10s %8s %-9s %6s %8s' % (
        'date', 'symbol', 'entry', 'sl', 'target', 'qty', 'status', 'exit_date', 'exit', 'why', 'R', 'pnl'))
    for r in rows:
        lines.append('%-10s %-12s %8s %8s %8s %4s %-15s %-10s %8s %-9s %6s %8s' % (
            r['date'], r['symbol'], r['entry'], r['sl'], r['target'], r['qty'], r['status'], r['exit_date'],
            r['exit'], r['reason_exit'], r['R'], r['pnl']))
    closed = [r for r in rows if r['status'] == 'CLOSED']
    cnt = collections.Counter(r['status'] for r in rows)
    lines.append('')
    lines.append('Status counts: ' + ', '.join('%s=%d' % kv for kv in sorted(cnt.items())))
    if closed:
        Rs = [r['R'] for r in closed]
        wins = sum(1 for x in Rs if x > 0)
        gp = sum(x for x in Rs if x > 0)
        gl = -sum(x for x in Rs if x < 0)
        lines.append('CLOSED trades: %d | win rate %d%% | avg R %.2f | profit factor %s | total pnl Rs %d' % (
            len(closed), round(100.0 * wins / len(closed)), sum(Rs) / len(closed),
            ('%.2f' % (gp / gl)) if gl > 0 else 'n/a', sum(r['pnl'] for r in closed)))
    else:
        lines.append('No closed trades yet.')
    n = len(closed)
    lines.append('Sample size: %d closed. Below ~30 trades the numbers mean very little; aim for 30-50 before judging.' % n)
    lines.append('Assumptions: daily bars only; if stop and target both fall in one day, stop counts first; entry at '
                 'max(open, trigger); skip if open >1.5%% above trigger; GTT alive %d trading days; time-stop after %d '
                 'days; cost %.2f%%. Not financial advice.' % (TRIGGER_DAYS, MAX_HOLD, COST_PCT))
    with open(os.path.join(out_dir, 'picks_review.txt'), 'w', encoding='utf-8') as h:
        h.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
