# Reel "SMC Power of 3" (Accumulation -> Manipulation -> Distribution), intraday, F&O stocks, 15-min Angel candles (~1 saal).
# Reel: din ka open = reference. Bullish din: bhav pehle open ke NEECHE jaata hai (manipulation: stop hunt, retail trap), phir
# structure palat'ta hai (MSS: pichhla chhota high toot'ta hai), FVG (fair value gap) par entry, SL manipulation ke low ke neeche,
# pehla target "internal range liquidity" (din ka pehle wala high), baaki aage. Bearish din ulta.
# Hamare rule (15-min):
#   dip: 9:15-11:15 me low < open x (1-0.2%). m = us ke baad ka sabse neecha low (MSS se pehle).
#   MSS: m ke baad koi candle close > SH (dip se m tak ke candles ka sabse uncha high), 13:00 tak. MSS_OPEN = close > open bhi.
#   Entry: (a) MSS candle close par; (b) FVG: MSS leg me bullish FVG (c[k-2].high < c[k].low), bhav wapas c[k].low tak aaye
#   (14:30 tak) to wahan limit entry.
#   SL = m - 0.05%. Risk 0.15%-3% ke beech warna skip.
#   Exit: 2R ya 15:15 | IRL (dip se pehle ka din high; entry ke upar na ho to 2R) ya 15:15 | sirf 15:15.
#   Kharcha: 0 aur 0.15% (round trip). Tulna: random din/time (10:00-13:00) par entry, SL = din ka ab tak ka low.
# usage: python po3_study.py   (data_orb/ me 15-min candles; data15 workflow / backup branch se)  -> out/po3_summary.txt
import os, random, collections
import orb_study

LINES = []
COSTS = (0.0, 0.0015)


def log(s=''):
    print(s, flush=True); LINES.append(s)


def flip(cs):
    """short ke liye bhav ulta (-x): long ka code hi short par chal jaata hai."""
    return [(t, -o, -l, -h, -c) for t, o, h, l, c in cs]


def run_exit(cs, j0, en, stop, tp):
    """j0 = entry ke baad pehla candle. Same candle me SL aur TP dono = SL."""
    for k in range(j0, len(cs)):
        t, o, h, l, c = cs[k]
        if l <= stop: return min(o, stop) if k > j0 else stop
        if tp is not None and h >= tp: return max(o, tp) if k > j0 else tp
    return cs[-1][4]


def setups(cs):
    """long setups ek din ke candles par: [(tag, entry_idx_exclusive, entry_px, stop, irl)]"""
    O = cs[0][1]; out = []
    i0 = next((i for i, x in enumerate(cs) if x[0] <= '11:15' and x[3] < O - 0.002 * abs(O)), None)
    if i0 is None: return out
    pre_hi = max(x[2] for x in cs[:i0 + 1])
    m, im = cs[i0][3], i0
    for k in range(i0, len(cs)):
        if cs[k][0] > '13:00': return out
        if cs[k][3] < m: m, im = cs[k][3], k
        sh = max(x[2] for x in cs[i0:im + 1])
        if k > im and cs[k][4] > sh:
            stop = m - 0.0005 * abs(m)
            out.append(('MSS (close par)', k + 1, cs[k][4], stop, pre_hi))
            if cs[k][4] > O: out.append(('MSS_OPEN (open ke upar bhi)', k + 1, cs[k][4], stop, pre_hi))
            top = None
            for q in range(max(im, 2), k + 1):
                if cs[q - 2][2] < cs[q][3]: top = cs[q][3]
            if top is not None:
                for q in range(k + 1, len(cs)):
                    if cs[q][0] > '14:30' or cs[q][3] <= stop: break
                    if cs[q][3] <= top:
                        en = min(cs[q][1], top)                 # gap neeche khula to open par
                        out.append(('FVG (gap par wapas aake)', q, en, stop, pre_hi, True)); break
            return out
    return out


def main():
    D = orb_study.load()
    dates = sorted({d for v in D.values() for d in v})
    log('SMC POWER OF 3 (reel) STUDY: %d stocks, %d din (%s se %s), 15-min candles' % (len(D), len(dates), dates[0], dates[-1]))
    R = collections.defaultdict(list); rnd = random.Random(3)
    half = dates[len(dates) // 2]
    for sym, byd in D.items():
        for d, cs0 in byd.items():
            for side in ('LONG', 'SHORT'):
                cs = cs0 if side == 'LONG' else flip(cs0)
                trades = []
                for s in setups(cs):
                    tag, j, en, stop, irl = s[:5]; same = len(s) > 5     # FVG: entry candle me hi SL check
                    trades.append((tag, j, en, stop, irl, same))
                # random tulna: 10:00-13:00 ka koi candle close, SL = ab tak ka din low
                ks = [k for k, x in enumerate(cs) if '10:00' <= x[0] <= '13:00']
                if ks and rnd.random() < 0.15:
                    k = rnd.choice(ks); trades.append(('BASE: random time', k + 1, cs[k][4], min(x[3] for x in cs[:k + 1]) - 0.0005 * abs(cs[k][4]), max(x[2] for x in cs[:k + 1]), False))
                for tag, j, en, stop, irl, same in trades:
                    risk = en - stop
                    if risk <= 0 or not (0.0015 <= abs(risk / en) <= 0.03) or j >= len(cs): continue
                    for ex_name, tp in (('2R ya 15:15', en + 2 * risk), ('IRL (din ka pehla high) ya 15:15', irl if irl > en + 0.3 * risk else en + 2 * risk), ('sirf 15:15', None)):
                        if same:                                  # FVG limit: usi candle me SL chhua to SL (bura maan ke)
                            ex = stop if cs[j][3] <= stop else (run_exit(cs, j + 1, en, stop, tp) if j + 1 < len(cs) else cs[j][4])
                        else:
                            ex = run_exit(cs, j, en, stop, tp)
                        for cost in COSTS:
                            r = (ex - en) / risk - cost * abs(en) / risk
                            for part in ('ALL', '1st half' if d < half else '2nd half'):
                                R[(side, tag, ex_name, cost, part)].append((d[:7], r))
    tags = ['BASE: random time', 'MSS (close par)', 'MSS_OPEN (open ke upar bhi)', 'FVG (gap par wapas aake)']
    log('R = risk ke hisaab se. "mahine+" = kitne mahine (10+ trade) avg plus. Kharcha 0.15% = brokerage+STT+slippage.')
    for side in ('LONG', 'SHORT'):
        for ex_name in ('2R ya 15:15', 'IRL (din ka pehla high) ya 15:15', 'sirf 15:15'):
            log(''); log('===== %s | exit: %s =====' % (side, ex_name))
            log('%-30s %-9s %6s %5s %9s %9s  %s' % ('setup', 'hissa', 'n', 'jeet', 'R (0 kh.)', 'R (0.15%)', 'mahine+'))
            for tg in tags:
                for part in ('ALL', '1st half', '2nd half'):
                    v0 = R.get((side, tg, ex_name, 0.0, part)); v1 = R.get((side, tg, ex_name, 0.0015, part))
                    if not v0: continue
                    mo = collections.defaultdict(list)
                    for m_, r in v1: mo[m_].append(r)
                    mp = sum(1 for m_ in mo if len(mo[m_]) >= 10 and sum(mo[m_]) > 0); mt = sum(1 for m_ in mo if len(mo[m_]) >= 10)
                    log('%-30s %-9s %6d %4.0f%% %+8.2fR %+8.2fR  %d/%d' % (tg, part, len(v0), 100.0 * sum(1 for x in v1 if x[1] > 0) / len(v1),
                        sum(x[1] for x in v0) / len(v0), sum(x[1] for x in v1) / len(v1), mp, mt))
    os.makedirs('out', exist_ok=True)
    open('out/po3_summary.txt', 'w').write('\n'.join(LINES) + '\n')


if __name__ == '__main__':
    main()
