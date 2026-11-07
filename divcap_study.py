# Reel test (7 Nov 2026): "ex-date se pehle kharido, dividend lo". Dividend capture: cum-date (ex se pehle ka din) CLOSE par kharido,
# ex-date OPEN ya CLOSE par becho, dividend jodo. Kharcha 0.25% (STT/brokerage), dividend par tax ~20% (slab, maan liya).
# Data: NSE corporate actions (dividend, ex-date) + bhavcopy (4 saal). Bucket: dividend yield. Tulna: tax se pehle bhi.
# usage: python divcap_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, json, re, datetime, collections, time
import results_study as rs

LINES = []
def log(s=''):
    print(s, flush=True); LINES.append(s)

def main():
    bhav, out = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'out'); os.makedirs(out, exist_ok=True)
    data = collections.defaultdict(dict)
    for fn in glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')):
        with open(fn, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[1].strip() != 'EQ': continue
                try:
                    d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
                    data[r[0].strip()][d] = (float(r[4]), float(r[8]), float(r[11]) / 100.0)
                except ValueError:
                    pass
    alld = sorted({d for v in data.values() for d in v})
    cache = os.path.join(out, 'divcap_ca.json')
    try: ev = json.load(open(cache))
    except Exception: ev = []
    if not ev:
        m = datetime.date(alld[0].year, alld[0].month, 1)
        while m <= alld[-1]:
            m2 = (m + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
            for _ in range(3):
                try:
                    ev += rs.nse('https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=%s&to_date=%s' % (m.strftime('%d-%m-%Y'), m2.strftime('%d-%m-%Y'))); break
                except Exception:
                    time.sleep(3)
            m = m2 + datetime.timedelta(days=1); time.sleep(0.5)
        json.dump(ev, open(cache, 'w'))
    R = collections.defaultdict(list)
    for e in ev:
        sub = (e.get('subject') or '')
        if 'dividend' not in sub.lower() or e.get('series') != 'EQ': continue
        amt = sum(float(x) for x in re.findall(r'(?:Rs\.?|Re\.?|₹)\s*-?\s*(\d+(?:\.\d+)?)', sub, re.I))
        try: xd = datetime.datetime.strptime(e['exDate'], '%d-%b-%Y').date()
        except Exception: continue
        byd = data.get(e['symbol'])
        if not amt or not byd or xd not in byd: continue
        prev = [d for d in alld if d < xd and d in byd][-1:]
        if not prev: continue
        c0 = byd[prev[0]][1]; o1, c1, to = byd[xd]
        y = amt / c0 * 100
        if y > 50: continue
        b = 'yield 5%+' if y >= 5 else 'yield 2-5%' if y >= 2 else 'yield 1-2%' if y >= 1 else 'yield <1%'
        for tag in ('SAB', b) + (('liquid (5cr+) sab',) if to >= 5 else ()):
            R[(tag, 'ex OPEN par becho (tax se pehle)')].append(((o1 + amt) / c0 - 1) * 100 - 0.25)
            R[(tag, 'ex OPEN par becho (20% tax baad)')].append(((o1 + 0.8 * amt) / c0 - 1) * 100 - 0.25)
            R[(tag, 'ex CLOSE par becho (20% tax baad)')].append(((c1 + 0.8 * amt) / c0 - 1) * 100 - 0.25)
            R[(tag, 'sirf bhav girawat ex OPEN (% dividend ka)')].append((c0 - o1) / amt * 100)
    log('DIVIDEND CAPTURE STUDY: %s se %s, %d dividend events' % (alld[0], alld[-1], len(R[('SAB', 'ex OPEN par becho (tax se pehle)')])))
    log('Kharido: ex-date se pehle din CLOSE. Kharcha 0.25%%. Aakhri line: ex-date open par share dividend ka kitna %% gira (100 = poora).')
    for t in ('SAB', 'liquid (5cr+) sab', 'yield <1%', 'yield 1-2%', 'yield 2-5%', 'yield 5%+'):
        log(''); log('== %s ==' % t)
        for k in ('ex OPEN par becho (tax se pehle)', 'ex OPEN par becho (20% tax baad)', 'ex CLOSE par becho (20% tax baad)', 'sirf bhav girawat ex OPEN (% dividend ka)'):
            v = R.get((t, k)) or []
            if not v: continue
            sv = sorted(v); med = sv[len(sv) // 2]
            if k.startswith('sirf'): log('  %-42s n=%5d  median %5.0f%%' % (k, len(v), med))
            else: log('  %-42s n=%5d  jeet %3.0f%%  avg %+6.2f%%  median %+6.2f%%' % (k, len(v), 100 * sum(1 for x in v if x > 0) / len(v), sum(v) / len(v), med))
    open(os.path.join(out, 'divcap_summary.txt'), 'w').write('\n'.join(LINES) + '\n')

if __name__ == '__main__':
    main()
