# Bade sauda (read-only, NSE public): bulk deals, block deals, insider trading (SEBI PIT) - pichhle 14 din.
# Writes docs/deals.json for the Swing Desk "Deals" tab. Sirf jaankari: iska backtest nahi hua, buy signal nahi.
# Never crashes: har source ka status json me rehta hai (ok / fail), taaki app "data nahi mila" dikha sake.
import os, sys, csv, io, json, re, datetime, traceback

from restrict import get, log, LOG      # same NSE session (cookie) + log helpers

DAYS = int(os.environ.get('DEALS_DAYS', '14'))
OUT = 'docs/deals.json'


def num(x):
    try:
        return float(str(x).replace(',', '').strip())
    except (ValueError, TypeError):
        return None


def pdate(x):
    x = str(x or '').strip()
    for f in ('%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y %H:%M', '%d-%b-%Y %H:%M:%S'):
        try:
            return datetime.datetime.strptime(x.title() if 'b' in f.lower() else x, f).date()
        except ValueError:
            pass
    m = re.match(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', x)
    if m:
        try:
            return datetime.datetime.strptime('%s-%s-%s' % (m.group(1), m.group(2).title(), m.group(3)), '%d-%b-%Y').date()
        except ValueError:
            pass
    return None


def rows_of(d):
    if isinstance(d, list):
        return [r for r in d if isinstance(r, dict)]
    if isinstance(d, dict):
        for k in ('data', 'Data', 'rows'):
            if isinstance(d.get(k), list):
                return [r for r in d[k] if isinstance(r, dict)]
    return []


def pick(r, *pats):
    """Pehli key jo kisi pattern se mile (NSE kabhi key naam badal deta hai)."""
    for p in pats:
        for k in r:
            if re.search(p, str(k), re.I):
                return r[k]
    return None


def side_of(x):
    x = str(x or '').upper()
    return 'BUY' if x.startswith('B') or 'PURCHASE' in x or 'ACQ' in x else 'SELL' if x.startswith('S') or 'DISP' in x else x[:12]


# ---------------- bulk / block ----------------
def deals_api(kind, fr, to, dbg):
    u = 'https://www.nseindia.com/api/historical/%s-deals?from=%s&to=%s' % (kind, fr.strftime('%d-%m-%Y'), to.strftime('%d-%m-%Y'))
    rows = rows_of(json.loads(get(u)))
    if rows and kind + '_keys' not in dbg:
        dbg[kind + '_keys'] = sorted(rows[0].keys())
    out = []
    for r in rows:
        d = pdate(pick(r, r'DATE', r'date'))
        sym = str(pick(r, r'SYMBOL', r'symbol') or '').strip().upper()
        qty = num(pick(r, r'QTY', r'quantity'))
        px = num(pick(r, r'WATP', r'PRICE', r'price'))
        if not d or not sym or not qty:
            continue
        out.append(dict(date=d.isoformat(), sym=sym, name=str(pick(r, r'SCRIP_NAME', r'NAME$', r'securityName') or '')[:60],
                        kind=kind.upper(), who=str(pick(r, r'CLIENT', r'client') or '')[:80],
                        side=side_of(pick(r, r'BUY_SELL', r'buySell', r'BUY')), qty=int(qty), price=px,
                        value_cr=round(qty * px / 1e7, 2) if px else None, note=str(pick(r, r'REMARK') or '').strip(' -')[:60]))
    return out


def deals_csv(kind, dbg):
    """Fallback: NSE archive ki aaj wali file (sirf latest din)."""
    txt = get('https://nsearchives.nseindia.com/content/equities/%s.csv' % kind, 'text/csv,*/*')
    rd = list(csv.DictReader(io.StringIO(txt)))
    if rd and kind + '_csv_keys' not in dbg:
        dbg[kind + '_csv_keys'] = list(rd[0].keys())
    out = []
    for r in rd:
        r = {str(k).strip(): v for k, v in r.items()}
        d = pdate(pick(r, r'^Date')); sym = str(pick(r, r'^Symbol') or '').strip().upper()
        qty = num(pick(r, r'Quantity')); px = num(pick(r, r'Price'))
        if not d or not sym or not qty:
            continue
        out.append(dict(date=d.isoformat(), sym=sym, name=str(pick(r, r'Security Name') or '')[:60], kind=kind.upper(),
                        who=str(pick(r, r'Client') or '')[:80], side=side_of(pick(r, r'Buy')), qty=int(qty), price=px,
                        value_cr=round(qty * px / 1e7, 2) if px else None, note=str(pick(r, r'Remarks') or '').strip(' -')[:60]))
    return out


# ---------------- insider (SEBI PIT) ----------------
INS_CATS = re.compile(r'promoter|director|kmp|key managerial|chairman|ceo|cfo|managing', re.I)


def insider(fr, to, dbg):
    u = 'https://www.nseindia.com/api/corporates-pit?index=equities&from_date=%s&to_date=%s' % (fr.strftime('%d-%m-%Y'), to.strftime('%d-%m-%Y'))
    rows = rows_of(json.loads(get(u)))
    if rows and 'pit_keys' not in dbg:
        dbg['pit_keys'] = sorted(rows[0].keys())
    out = []
    for r in rows:
        sym = str(pick(r, r'^symbol$') or '').strip().upper()
        cat = str(pick(r, r'personCategory', r'category') or '')
        typ = str(pick(r, r'tdpTransactionType', r'transactionType', r'acqType') or '')
        mode = str(pick(r, r'acqMode', r'mode') or '')
        qty = num(pick(r, r'^secAcq$', r'noOfShare', r'quantity'))
        val = num(pick(r, r'^secVal$', r'value'))
        d = pdate(pick(r, r'^acqtoDt$', r'^acqfromDt$', r'^date$')) or pdate(pick(r, r'intimDt'))
        if not sym or not qty or not d:
            continue
        if not INS_CATS.search(cat):                      # sirf promoter/director/KMP: asli 'andar wale'
            continue
        if re.search(r'pledge|revok|invoc|esop|allot|gift|inherit|transmission', typ + ' ' + mode, re.I):
            continue                                       # girvi/ESOP/gift: bazaar me kharid-bikri nahi
        side = side_of(typ)
        if side not in ('BUY', 'SELL'):
            continue
        bef, aft = num(pick(r, r'befAcqSharesPer')), num(pick(r, r'afterAcqSharesPer'))
        out.append(dict(date=d.isoformat(), sym=sym, name=str(pick(r, r'company') or '')[:60], kind='INSIDER',
                        who=str(pick(r, r'acqName', r'name') or '')[:80], cat=cat[:40], side=side, qty=int(qty),
                        price=round(val / qty, 2) if val and qty else None, value_cr=round(val / 1e7, 2) if val else None,
                        note=(mode[:40] + ('; holding %.2f%% -> %.2f%%' % (bef, aft) if bef is not None and aft is not None else '')).strip('; ')))
    return out


def main():
    ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    to = ist.date(); fr = to - datetime.timedelta(days=DAYS)
    try:
        get('https://www.nseindia.com/', 'text/html,*/*', tries=1)
    except Exception as e:
        log('warmup fail: %s' % str(e)[:80])
    dbg, status, allr = {}, {}, []
    for kind in ('bulk', 'block'):
        try:
            r = deals_api(kind, fr, to, dbg); status[kind] = 'ok api (%d)' % len(r)
        except Exception as e:
            log('%s api fail: %s' % (kind, str(e)[:100]))
            try:
                r = deals_csv(kind, dbg); status[kind] = 'ok csv-latest (%d)' % len(r)
            except Exception as e2:
                r = []; status[kind] = 'fail'; log('%s csv fail: %s' % (kind, str(e2)[:100]))
        allr += r
    try:
        r = insider(fr, to, dbg); status['insider'] = 'ok (%d)' % len(r); allr += r
    except Exception as e:
        status['insider'] = 'fail'; log('insider fail: %s' % str(e)[:120])
    # purani file ke deals rakho (csv fallback sirf ek din deta hai), 14 din se purane hatao, duplicate hatao
    old = []
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding='utf-8')).get('deals', [])
        except Exception:
            pass
    seen, deals = set(), []
    for x in allr + old:
        k = (x.get('date'), x.get('sym'), x.get('kind'), x.get('who'), x.get('side'), x.get('qty'))
        if k in seen or (x.get('date') or '') < fr.isoformat():
            continue
        seen.add(k); deals.append(x)
    deals.sort(key=lambda x: (x['date'], x.get('value_cr') or 0), reverse=True)
    log('status: %s | deals kept: %d' % (json.dumps(status), len(deals)))
    os.makedirs('docs', exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as h:
        json.dump({'updated': ist.strftime('%Y-%m-%d %H:%M IST'), 'from': fr.isoformat(), 'status': status, 'deals': deals,
                   'debug': dbg, 'log': LOG[-15:]}, h, ensure_ascii=False, separators=(',', ':'))
    print('wrote', OUT, len(deals))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('deals.py error:', traceback.format_exc()[-500:]); sys.exit(1)
