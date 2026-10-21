# "Result ke baad trade" (post-result drift) test. User ka idea: result live padho, agle din result + reaction dekh ke trade.
# NSE: har quarterly result ki broadcast date/time (corporates-financial-results, mahine-war). Reaction din = result ke baad pehla
# poora trading din (market ke baad ya din me aaya result -> agla din; subah 9:15 se pehle -> usi din).
# Reaction din par: gap (open vs kal close), din ka return, volume vs 20-din avg. Phir alag-alag rule se entry, 5/10/20 din rakho
# (SL 2 ATR). Tulna: saare results ka average aur random din. Kharcha 0.25%, liquid stocks (20-din turnover 5 cr+).
# usage: python results_study.py <bhav_folder> <out_folder>
import os, sys, csv, glob, json, time, random, datetime, collections, urllib.request, http.cookiejar

LINES = []
CACHE = 'out/results_dates.json'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def log(s=''):
    print(s, flush=True); LINES.append(s)


def nse(u):
    r = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': 'application/json', 'Referer': 'https://www.nseindia.com/'})
    return json.loads(_op.open(r, timeout=60).read().decode('utf-8', 'ignore'))


def result_dates(d0, d1):
    """[(symbol, 'YYYY-MM-DD HH:MM')]: NSE corporate announcements me 'Outcome of Board Meeting' jisme financial results ki baat ho
    (2025 se NSE ka purana results API khaali aata hai). Hafte-hafte, cache out/results_dates.json."""
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    w = d0
    while w <= d1:
        w2 = min(d1, w + datetime.timedelta(days=6)); key = w.isoformat()
        if key not in cache or w2 > datetime.date.today() - datetime.timedelta(days=3):
            got, err = None, ''
            for attempt in range(3):
                try:
                    got = nse('https://www.nseindia.com/api/corporate-announcements?index=equities&from_date=%s&to_date=%s'
                              % (w.strftime('%d-%m-%Y'), w2.strftime('%d-%m-%Y')))
                    break
                except Exception as e:
                    err = str(e); time.sleep(3 * (attempt + 1))
            if got is None:
                log('NSE %s FAIL %s' % (key, err[:60])); w = w2 + datetime.timedelta(days=1); continue
            ev = {}
            for r in got:
                if (r.get('desc') or '') != 'Outcome of Board Meeting':
                    continue
                tx = (r.get('attchmntText') or '').lower()
                if 'result' not in tx or ('financial' not in tx and 'quarter' not in tx):
                    continue
                s_ = (r.get('symbol') or '').strip()
                try:
                    dt = datetime.datetime.strptime((r.get('sort_date') or '')[:16], '%Y-%m-%d %H:%M')
                except ValueError:
                    continue
                if s_ and (s_ not in ev or dt < ev[s_]):
                    ev[s_] = dt
            cache[key] = [[k, v.strftime('%Y-%m-%d %H:%M')] for k, v in ev.items()]
            time.sleep(0.8)
        w = w2 + datetime.timedelta(days=1)
    os.makedirs('out', exist_ok=True)
    json.dump(cache, open(CACHE, 'w'), separators=(',', ':'))
    seen, out = set(), []
    for v in cache.values():
        for sym, t in v:
            k = (sym, t[:7])                       # ek mahine me ek hi result maano
            if k not in seen:
                seen.add(k); out.append((sym, t))
    return out


def main():
    bhav, out_dir = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'out')
    os.makedirs(out_dir, exist_ok=True)
    data = collections.defaultdict(dict)
    for fn in glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')):
        with open(fn, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15 or r[1].strip() != 'EQ': continue
                try:
                    d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
                    t = (float(r[4]), float(r[5]), float(r[6]), float(r[8]), float(r[10]), float(r[11]) / 100.0)
                except ValueError:
                    continue
                if t[3] > 0: data[r[0].strip()][d] = t
    alld = sorted({d for v in data.values() for d in v})
    log('RESULT KE BAAD TRADE (post-result drift) STUDY (%s): bhav %s se %s, %d stocks' % (datetime.date.today(), alld[0], alld[-1], len(data)))
    ev = result_dates(alld[0], alld[-1])
    log('NSE results mile: %d' % len(ev))
    # market haal
    ab, tot = collections.Counter(), collections.Counter(); a50 = 2.0 / 51
    for byd in data.values():
        ds = sorted(byd); e = None
        for k, d in enumerate(ds):
            c = byd[d][3]; e = c if e is None else a50 * c + (1 - a50) * e
            if k >= 60 and byd[d][5] >= 1: tot[d] += 1; ab[d] += c > e
    reg = {d: ('STRONG' if 100.0 * ab[d] / tot[d] >= 60 else 'MIXED' if 100.0 * ab[d] / tot[d] >= 40 else 'WEAK' if 100.0 * ab[d] / tot[d] >= 25 else 'VWEAK')
           for d in alld if tot[d] >= 50}
    idx = {}
    for sym, byd in data.items():
        idx[sym] = sorted(byd)
    R = collections.defaultdict(list); rnd = random.Random(5); n_ev = 0
    HOLDS = (5, 10, 20)

    def trade(sym, i_sig, entry_at_close, tag, rg, yr):
        ds = idx[sym]; b = [data[sym][d] for d in ds]
        o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]
        if i_sig + 1 >= len(c): return
        tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(max(1, i_sig - 13), i_sig + 1)]
        atr = sum(tr) / len(tr)
        if entry_at_close:
            e, j0 = c[i_sig], i_sig + 1
        else:
            j = i_sig + 1
            if o[j] > c[i_sig] * 1.03 or o[j] < c[i_sig] * 0.97: return     # agle din bada gap: skip
            e, j0 = o[j], j
        stop = e - 2 * atr
        for hold in HOLDS:
            ex = None
            for k in range(j0, min(len(c), j0 + hold)):
                if l[k] <= stop:
                    ex = min(o[k], stop) if (k > j0 or entry_at_close) else stop; break
            if ex is None:
                k = min(len(c), j0 + hold) - 1; ex = c[k]
            pc = (ex / e - 1) * 100 - 0.25
            for rk in (rg, 'ALL'):
                R[(tag, hold, rk)].append((yr, pc))

    for sym, t in ev:
        if sym not in data: continue
        dt = datetime.datetime.strptime(t, '%Y-%m-%d %H:%M'); ds = idx[sym]
        # reaction din: 9:15 se pehle -> usi din, warna agla trading din
        rd_ = dt.date() if dt.hour * 60 + dt.minute < 9 * 60 + 15 else dt.date() + datetime.timedelta(days=1)
        i = next((k for k, d in enumerate(ds) if d >= rd_), None)
        if i is None or i < 25 or (ds[i] - rd_).days > 5: continue
        b = [data[sym][d] for d in ds[i - 21:i + 1]]
        if sum(x[5] for x in b[:-1]) / 20.0 < 5: continue                  # liquid nahi
        o, h, l, c, v = b[-1][0], b[-1][1], b[-1][2], b[-1][3], b[-1][4]
        pc_ = b[-2][3]; vx = v / (sum(x[4] for x in b[:-1]) / 20.0)
        gap = (o / pc_ - 1) * 100; day = (c / pc_ - 1) * 100; hold_gain = c >= o
        if any(abs(b[k][3] / b[k - 1][3] - 1) > 0.35 for k in range(1, len(b))): continue
        n_ev += 1; rg = reg.get(ds[i], '?'); yr = ds[i].year
        trade(sym, i, True, 'ALL results: reaction din close par', rg, yr)
        if day >= 4 and vx >= 3: trade(sym, i, True, 'UP4+VOL3: close par', rg, yr); trade(sym, i, False, 'UP4+VOL3: agle din open', rg, yr)
        if day >= 8 and vx >= 3: trade(sym, i, True, 'UP8+VOL3: close par', rg, yr)
        if gap >= 3 and hold_gain and vx >= 2: trade(sym, i, True, 'GAP3 + din bhar tika (close>=open)', rg, yr)
        if gap >= 3 and not hold_gain: trade(sym, i, True, 'GAP3 par din me gira (close<open)', rg, yr)
        if day <= -4 and vx >= 3: trade(sym, i, True, 'DOWN4+VOL3 (bura result): close par', rg, yr)
        if 0 <= day < 4: trade(sym, i, True, 'Result ke baad 0-4% (normal)', rg, yr)
    # random base: koi bhi liquid din
    for sym, ds in idx.items():
        for i in range(25, len(ds) - 1):
            if rnd.random() > 0.004: continue
            b = [data[sym][d] for d in ds[i - 21:i + 1]]
            if sum(x[5] for x in b[:-1]) / 20.0 < 5: continue
            trade(sym, i, True, 'BASE: random din', reg.get(ds[i], '?'), ds[i].year)
    log('Liquid result events (reaction din ke saath): %d' % n_ev)
    log('avg%% = kharcha (0.25%%) kaat ke, SL 2 ATR. "saal+" = kitne saal (20+ trade) avg plus.')
    tags = ['BASE: random din', 'ALL results: reaction din close par', 'Result ke baad 0-4% (normal)', 'UP4+VOL3: close par', 'UP4+VOL3: agle din open',
            'UP8+VOL3: close par', 'GAP3 + din bhar tika (close>=open)', 'GAP3 par din me gira (close<open)', 'DOWN4+VOL3 (bura result): close par']
    for hold in HOLDS:
        log(''); log('===== %d din rakho =====' % hold)
        log('%-40s %-7s %6s %5s %8s  %s' % ('rule', 'market', 'n', 'jeet', 'avg%', 'saal+'))
        for tg in tags:
            for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
                v = R.get((tg, hold, rk))
                if not v or (rk != 'ALL' and len(v) < 30): continue
                yrs = collections.defaultdict(list)
                for y, p in v: yrs[y].append(p)
                yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
                log('%-40s %-7s %6d %4.0f%% %+7.2f%%  %d/%d' % (tg, rk, len(v), 100.0 * sum(1 for x in v if x[1] > 0) / len(v), sum(x[1] for x in v) / len(v), yp, yt))
    open(os.path.join(out_dir, 'results_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
