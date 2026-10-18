# Har stock ki apni strategy? Owner ka idea: achhe move wale stock chuno, har stock pe dekho kaunsa setup usme chala,
# phir usi stock pe wahi setup lagao. Imaandar test: setup sirf 2022-24 (TRAIN) se chuna jaata hai, 2025-26 (TEST) pe
# bina badle check hota hai. Tulna: sab stocks pe ek hi setup (TRAIN se chuna), aur random setup chunna.
# Input: regime_study.py ko TRADES=1 ke saath chalao -> out/regime_trades.csv.gz + out/stock_stats.csv
# usage: python stock_study.py out   -> out/stock_summary.txt, out/stock_results.csv
import csv, gzip, os, sys, random, collections, datetime

out_dir = sys.argv[1] if len(sys.argv) > 1 else 'out'
SPLIT = os.environ.get('SPLIT', '2025-01-01')
TRAIN_FROM = os.environ.get('TRAIN_FROM', '')      # jaise 2025-01-01: sirf mandi wale saal se seekho
TOPN = int(os.environ.get('TOPN', '50'))
PICK = os.environ.get('PICK', 'atr')       # atr = sabse zyada roz-move; turnover = sabse bade/stable (sabse zyada kaarobar)
SUF = ('' if PICK == 'atr' else '_' + PICK) + os.environ.get('SUFX', '')
MIN_TRAIN = int(os.environ.get('MIN_TRAIN', '6'))                  # ek stock pe ek setup ke kam se kam itne TRAIN trades, tabhi chuna ja sakta hai
L = []


def log(s=''):
    print(s, flush=True); L.append(s)


def avg(x):
    return sum(x) / len(x) if x else 0.0


def stat(rs):
    return dict(n=len(rs), avg=avg(rs), win=round(100.0 * sum(1 for r in rs if r > 0) / len(rs)) if rs else 0)


def spearman(a, b):
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for k, i in enumerate(o): r[i] = k
        return r
    ra, rb = rk(a), rk(b); n = len(a)
    if n < 3: return 0.0
    ma, mb = avg(ra), avg(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)); va = sum((x - ma) ** 2 for x in ra); vb = sum((y - mb) ** 2 for y in rb)
    return cov / (va * vb) ** 0.5 if va and vb else 0.0


stats = {}
for r in csv.DictReader(open(os.path.join(out_dir, 'stock_stats.csv'))):
    try:
        stats[r['sym']] = dict(liq=int(r['liq_days']), days=int(r['days']), atr=float(r['atr_pct_med']), up=float(r['above50_pct']),
                              to=float(r.get('turnover_cr_med') or 0))
    except ValueError:
        pass
elig = [s for s, v in stats.items() if v['days'] >= 400 and v['liq'] >= 0.8 * v['days']]
U = sorted(elig, key=lambda s: -stats[s]['to' if PICK == 'turnover' else 'atr'])[:TOPN]   # 2024 tak ke data se
US = set(U)
T = collections.defaultdict(lambda: collections.defaultdict(lambda: ([], [])))   # sym -> (setup,exit) -> (train[], test[])
REGT = collections.defaultdict(lambda: ([], []))                                 # (setup,exit,regime) -> train/test (sab stock)
ALLTEST = []
with gzip.open(os.path.join(out_dir, 'regime_trades.csv.gz'), 'rt') as h:
    for r in csv.DictReader(h):
        if r['setup'] == 'STRUCT_ALL': continue
        if r['date'] < TRAIN_FROM: continue
        R = float(r['R']); tr = r['date'] < SPLIT; k = (r['setup'], r['exit'])
        REGT[(r['setup'], r['exit'], r['regime'])][0 if tr else 1].append(R)
        if r['sym'] in US:
            T[r['sym']][k][0 if tr else 1].append((R, r['regime']))
            if not tr: ALLTEST.append(R)

log('HAR STOCK KI APNI STRATEGY - TEST (generated %s)' % datetime.date.today())
log('TRAIN %s se %s tak, TEST %s se.' % (TRAIN_FROM or 'shuru', SPLIT, SPLIT))
log('Universe: %d stock (liquid 80%%+ din, 2024 tak ke data se %s). TRAIN < %s, TEST >= %s.' % (len(U), 'sabse zyada turnover (bade stock)' if PICK == 'turnover' else 'sabse zyada roz-move/ATR%', SPLIT, SPLIT))
log('Har stock pe har (setup, exit) jisme TRAIN me %d+ trade: TRAIN me sabse achha chuna, TEST me wahi lagaya.' % MIN_TRAIN)
log('')

# 1) per-stock best
pick, rows = {}, []
for s in U:
    best = None
    for k, (tr, te) in T[s].items():
        if len(tr) < MIN_TRAIN: continue
        a = avg([x for x, _ in tr])
        if a > 0 and (best is None or a > best[1]): best = (k, a)
    if best: pick[s] = best[0]
ps_test = [x for s, k in pick.items() for x, _ in T[s][k][1]]
# 1b) per-stock best + regime filter: sirf un regime me jahan wo setup (sab stock milake) TRAIN me plus tha
regok = {k: avg(v[0]) > 0 for k, v in REGT.items() if len(v[0]) >= 30}
ps_reg = [x for s, k in pick.items() for x, rg in T[s][k][1] if regok.get((k[0], k[1], rg))]
# 2) ek hi setup sab pe (TRAIN me in stocks pe pooled best)
pool = collections.defaultdict(lambda: ([], []))
for s in U:
    for k, (tr, te) in T[s].items():
        pool[k][0].extend(x for x, _ in tr); pool[k][1].extend(x for x, _ in te)
gk = max((k for k in pool if len(pool[k][0]) >= 100), key=lambda k: avg(pool[k][0]))
g_test = pool[gk][1]
dip = pool.get(('DIP_A', '2ATR/5d'), ([], []))[1]
# 3) random setup per stock (200 baar), wahi MIN_TRAIN shart
rnd = random.Random(1); ravg = []
for _ in range(200):
    v = []
    for s in U:
        c = [k for k, (tr, te) in T[s].items() if len(tr) >= MIN_TRAIN]
        if c: v.extend(x for x, _ in T[s][rnd.choice(c)][1])
    ravg.append(avg(v))
ravg.sort()

log('== TEST (%s se) me nateeja, R per trade (kharcha kaat ke) ==' % SPLIT)
for name, rs in (('A. Har stock ki apni strategy (TRAIN se chuni)', ps_test),
                 ('B. Apni strategy + market-haal filter', ps_reg),
                 ('C. Sab stock pe ek hi setup: %s %s' % gk, g_test),
                 ('D. Sab stock pe Dip A (2ATR/5d)', dip),
                 ('E. In stocks ke saare signal (koi chunav nahi)', ALLTEST)):
    st = stat(rs); log('  %-55s n %5d  avgR %+.3f  jeet %d%%' % (name, st['n'], st['avg'], st['win']))
log('  %-55s avgR %+.3f (5%%-95%%: %+.3f .. %+.3f)' % ('F. Har stock pe random setup (200 baar)', avg(ravg), ravg[10], ravg[189]))
log('')
# persistence: kya stock+setup ka TRAIN result TEST ka andaza deta hai?
a_, b_ = [], []
for s in U:
    for k, (tr, te) in T[s].items():
        if len(tr) >= MIN_TRAIN and len(te) >= MIN_TRAIN:
            a_.append(avg([x for x, _ in tr])); b_.append(avg([x for x, _ in te]))
rho = spearman(a_, b_)
log('Kya pichhla result aage ka andaza deta hai? %d (stock, setup) jode, rank correlation TRAIN vs TEST = %+.2f' % (len(a_), rho))
log('  (0 = koi rishta nahi, kismat; +0.3 se upar = kaam ka rishta)')
top = sorted(range(len(a_)), key=lambda i: -a_[i])[:max(1, len(a_) // 5)]
log('  TRAIN ke top 20%% jode: TRAIN avg %+.3f -> TEST avg %+.3f' % (avg([a_[i] for i in top]), avg([b_[i] for i in top])))
log('')
log('== Har stock (chuna hua setup) ==')
log('%-12s %6s  %-16s %-16s %5s %7s %5s %7s' % ('stock', 'ATR%', 'setup', 'exit', 'nTr', 'trainR', 'nTe', 'testR'))
pos = 0; tested = 0
for s in U:
    if s not in pick:
        log('%-12s %6.2f  (koi setup TRAIN me plus nahi / trade kam)' % (s, stats[s]['atr'])); continue
    k = pick[s]; tr, te = T[s][k]; ta = avg([x for x, _ in te]) if te else None
    if te: tested += 1; pos += ta > 0
    rows.append(dict(sym=s, atr_pct=stats[s]['atr'], setup=k[0], exit=k[1], n_train=len(tr), trainR=round(avg([x for x, _ in tr]), 3),
                     n_test=len(te), testR=round(ta, 3) if ta is not None else ''))
    log('%-12s %6.2f  %-16s %-16s %5d %+7.3f %5d %7s' % (s, stats[s]['atr'], k[0], k[1], len(tr), avg([x for x, _ in tr]), len(te),
                                                       '%+.3f' % ta if ta is not None else '-'))
log('')
log('TEST me plus rahe: %d / %d stock (jinke TEST trade the).' % (pos, tested))
log('Dhyan: ek stock pe ek setup ke saal me sirf kuch trade bante hain, isliye har stock ka number akela bharose layak nahi.')
open(os.path.join(out_dir, 'stock_summary%s.txt' % SUF), 'w').write('\n'.join(L) + '\n')
if rows:
    with open(os.path.join(out_dir, 'stock_results%s.csv' % SUF), 'w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
