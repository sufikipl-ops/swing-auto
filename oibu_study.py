# Reel (order-block.com dashboard): "Long build-up" = bhav upar + futures OI (khule saude) bhi upar -> bullish. Swing version test.
# Data: NSE F&O bhavcopy (har din, har stock future ka OI). OI badlav sirf un contracts se jo aaj expire nahi ho rahe
# (OpnIntrst - ChngInOpnIntrst = kal ka OI), taaki expiry/rollover se nakli girawat na aaye. Cache: out/fo_oi.json
# Setups (aaj ke close par, kal OPEN par entry, gap +1.5%/-3% skip, SL 2 ATR, kharcha 0.25%, 2/5/10 din):
#   UP2_ANY       : bhav +2%+ (OI kuch bhi)  -> OI ke bina kitna milta, tulna ke liye
#   LONG_BU       : bhav +2%+, OI +5%+
#   LONG_BU_STRONG: bhav +3%+, OI +10%+, volume 1.5x+
#   LONG_BU_TOP5  : us din ke LONG_BU me bhav ke hisaab se top 5 (dashboard ka "PICK BULLISH #1" jaisa)
#   SHORT_COVER   : bhav +2%+, OI -5% ya kam (shorts bhaag rahe)
#   SHORT_BU      : bhav -2% ya kam, OI +5%+ (bearish; kharidna kaisa?)
#   LONG_UNWIND   : bhav -2% ya kam, OI -5% ya kam
#   BASE          : random F&O stock din
# usage: python oibu_study.py <bhav_folder> <out_folder>
import os, sys, csv, io, json, glob, time, random, zipfile, datetime, collections, urllib.request

LINES = []
CACHE = 'out/fo_oi.json'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
MON = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']


def log(s=''):
    print(s, flush=True); LINES.append(s)


def get(u):
    r = urllib.request.Request(u, headers={'User-Agent': UA, 'Referer': 'https://www.nseindia.com/'})
    return urllib.request.urlopen(r, timeout=60).read()


def fo_day(d):
    """{sym: [oi_aaj, oi_kal]} stock futures, sirf wo contracts jo d ke baad expire hote hain. None = file nahi (chhutti)."""
    rows = None
    for u, new in (('https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_%s_F_0000.csv.zip' % d.strftime('%Y%m%d'), True),
                   ('https://nsearchives.nseindia.com/content/historical/DERIVATIVES/%d/%s/fo%02d%s%dbhav.csv.zip' % (d.year, MON[d.month - 1], d.day, MON[d.month - 1], d.year), False)):
        if new and d < datetime.date(2024, 7, 1): continue
        if not new and d >= datetime.date(2024, 7, 13): continue
        for attempt in range(3):
            try:
                z = zipfile.ZipFile(io.BytesIO(get(u))); rows = list(csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), 'utf-8', errors='ignore'))); break
            except urllib.error.HTTPError as e:
                if e.code == 404: break
                time.sleep(2 * (attempt + 1))
            except Exception:
                time.sleep(2 * (attempt + 1))
        if rows is not None:
            break
    if rows is None:
        return None
    out = collections.defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        try:
            if 'FinInstrmTp' in r:
                if r['FinInstrmTp'] != 'STF': continue
                sym, ex = r['TckrSymb'].strip(), datetime.date.fromisoformat(r['XpryDt'][:10])
                oi, ch = float(r['OpnIntrst'] or 0), float(r['ChngInOpnIntrst'] or 0)
            else:
                if r['INSTRUMENT'].strip() != 'FUTSTK': continue
                sym, ex = r['SYMBOL'].strip(), datetime.datetime.strptime(r['EXPIRY_DT'].strip(), '%d-%b-%Y').date()
                oi, ch = float(r['OPEN_INT'] or 0), float(r['CHG_IN_OI'] or 0)
        except (ValueError, KeyError):
            continue
        if ex <= d: continue
        out[sym][0] += oi; out[sym][1] += oi - ch
    return dict(out)


def load_oi(days):
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    n_new = 0
    for d in days:
        k = d.isoformat()
        if k in cache: continue
        v = fo_day(d)
        cache[k] = v or {}; n_new += 1; time.sleep(0.3)
        if n_new % 100 == 0:
            log('F&O OI: %d naye din aaye...' % n_new); json.dump(cache, open(CACHE, 'w'), separators=(',', ':'))
    os.makedirs('out', exist_ok=True)
    json.dump(cache, open(CACHE, 'w'), separators=(',', ':'))
    return cache


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
    ab, tot = collections.Counter(), collections.Counter(); a50 = 2.0 / 51
    for byd in data.values():
        ds = sorted(byd); e = None
        for k, d in enumerate(ds):
            c = byd[d][3]; e = c if e is None else a50 * c + (1 - a50) * e
            if k >= 60 and byd[d][5] >= 1: tot[d] += 1; ab[d] += c > e
    reg = {d: ('STRONG' if 100.0 * ab[d] / tot[d] >= 60 else 'MIXED' if 100.0 * ab[d] / tot[d] >= 40 else 'WEAK' if 100.0 * ab[d] / tot[d] >= 25 else 'VWEAK')
           for d in alld if tot[d] >= 50}
    OI = load_oi(alld)
    have = sum(1 for d in alld if OI.get(d.isoformat()))
    log('LONG BUILD-UP (futures OI) STUDY (%s): %s se %s, %d stocks, F&O OI %d din' % (datetime.date.today(), alld[0], alld[-1], len(data), have))
    # pehle har din ke signals, phir top5
    sig = collections.defaultdict(list)            # (sym, i) -> tags
    cand = collections.defaultdict(list)           # date -> [(chg, sym, i)] LONG_BU
    rnd = random.Random(13); HOLDS = (2, 5, 10)
    series = {}
    for sym, byd in data.items():
        ds = sorted(byd)
        if len(ds) < 40: continue
        series[sym] = ds
        b = [byd[d] for d in ds]; c = [x[3] for x in b]; v = [x[4] for x in b]
        for i in range(25, len(c) - 1):
            o_ = OI.get(ds[i].isoformat(), {}).get(sym)
            if not o_ or o_[1] <= 0: continue
            if any(abs(c[k] / c[k - 1] - 1) > 0.35 for k in range(i - 21, i + 1)): continue
            chg = (c[i] / c[i - 1] - 1) * 100; oic = (o_[0] / o_[1] - 1) * 100; vx = v[i] / (sum(v[i - 20:i]) / 20.0)
            t = []
            if chg >= 2: t.append('UP2_ANY (sirf bhav +2%)')
            if chg >= 2 and oic >= 5: t.append('LONG_BU (bhav+2%, OI+5%)'); cand[ds[i]].append((chg, sym, i))
            if chg >= 3 and oic >= 10 and vx >= 1.5: t.append('LONG_BU_STRONG (+3%, OI+10%, vol)')
            if chg >= 2 and oic <= -5: t.append('SHORT_COVER (bhav+, OI-)')
            if chg <= -2 and oic >= 5: t.append('SHORT_BU (bhav-, OI+)')
            if chg <= -2 and oic <= -5: t.append('LONG_UNWIND (bhav-, OI-)')
            if rnd.random() < 0.02: t.append('BASE: random F&O din')
            if t: sig[(sym, i)] += t
    for d, L in cand.items():
        for chg, sym, i in sorted(L, reverse=True)[:5]:
            sig[(sym, i)].append('LONG_BU_TOP5 (din ke top 5)')
    R = collections.defaultdict(list)
    for (sym, i), tags in sig.items():
        ds = series[sym]; byd = data[sym]; b = [byd[d] for d in ds]
        o = [x[0] for x in b]; h = [x[1] for x in b]; l = [x[2] for x in b]; c = [x[3] for x in b]
        j = i + 1
        if o[j] > c[i] * 1.015 or o[j] < c[i] * 0.97: continue
        tr = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - 13, i + 1)]; atr = sum(tr) / 14.0
        en = o[j]; stop = en - 2 * atr
        for hold in HOLDS:
            ex = None
            for k in range(j, min(len(c), j + hold)):
                if l[k] <= stop: ex = stop if k == j else min(o[k], stop); break
            if ex is None: ex = c[min(len(c), j + hold) - 1]
            pc = (ex / en - 1) * 100 - 0.25
            for tg in tags:
                for rk in (reg.get(ds[i], '?'), 'ALL'):
                    R[(tg, hold, rk)].append((ds[i].year, pc))
    tags = ['BASE: random F&O din', 'UP2_ANY (sirf bhav +2%)', 'LONG_BU (bhav+2%, OI+5%)', 'LONG_BU_STRONG (+3%, OI+10%, vol)',
            'LONG_BU_TOP5 (din ke top 5)', 'SHORT_COVER (bhav+, OI-)', 'SHORT_BU (bhav-, OI+)', 'LONG_UNWIND (bhav-, OI-)']
    log('avg% = kharcha (0.25%) kaat ke, SL 2 ATR, kal open par entry. "saal+" = kitne saal (20+ trade) avg plus.')
    for hold in HOLDS:
        log(''); log('===== %d din rakho =====' % hold)
        log('%-36s %-7s %6s %5s %8s  %s' % ('setup', 'market', 'n', 'jeet', 'avg%', 'saal+'))
        for tg in tags:
            for rk in ('ALL', 'STRONG', 'MIXED', 'WEAK', 'VWEAK'):
                vv = R.get((tg, hold, rk))
                if not vv or (rk != 'ALL' and len(vv) < 30): continue
                yrs = collections.defaultdict(list)
                for y, p in vv: yrs[y].append(p)
                yp = sum(1 for y in yrs if len(yrs[y]) >= 20 and sum(yrs[y]) > 0); yt = sum(1 for y in yrs if len(yrs[y]) >= 20)
                log('%-36s %-7s %6d %4.0f%% %+7.2f%%  %d/%d' % (tg, rk, len(vv), 100.0 * sum(1 for x in vv if x[1] > 0) / len(vv), sum(x[1] for x in vv) / len(vv), yp, yt))
    open(os.path.join(out_dir, 'oibu_summary.txt'), 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
