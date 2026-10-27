# Swing Desk: handoff for a new Claude session

Owner: Sufiyan (Surat, part-time NSE swing trader). Capital Rs 50,000, max loss/day Rs 500-1,000, max 2 trades/day,
delivery holds 2-5 days, never options. Speaks Hinglish: reply in simple Hinglish, give click-level steps,
do the coding yourself (edit, test, commit, merge to main). Do not make him upload files.

## Pieces
- GitHub Pages app: docs/index.html (single-file vanilla JS PWA, "Swing Desk"). Tabs: Picks, Search, Trades, News, Global.
- Google Sheet 1KNw0jZTk29jwo2ohxdYl11CNxXAvOTcE4Y4lG1Vromw (tabs Screen, Picks, Pins, Settings, Live, TG) + Apps Script
  web app (PinsApi.gs, NOT in GitHub; he pastes it into Apps Script manually and deploys via Manage deployments -> Edit ->
  New version, never a new deployment: the /exec URL is hard-coded in docs/index.html). Live prices, locks, Telegram notes
  and alert push go through it. Telegram notes now come by POLLING (setupTelegramPolling, 5-min trigger tgPoll) because the
  webhook got "302 Found" from Apps Script and Telegram stalled (fixed 2026-10-17; bot token was rotated).
  The Google Sheets connector (if attached) can read the TG/Picks/Settings tabs directly for debugging.
- Actions (workflows in .github/workflows): screen, dip (evening), news (every 20 min in market hours), live (every ~25 s
  market hours, Angel One quotes -> Sheet; also runs watch_alerts.py -> Telegram IGNORE alerts), gap, restrict (ASM/GSM/
  circuit via NSE), global (Yahoo indices/commodities/big stocks + headlines), review (nightly picks_review.py),
  names, funda (19:25 IST: promoter pledge/holding from NSE, D/E + PE/ROE/growth from Yahoo -> docs/funda.json),
  app (stocks.json; also 19:50 backup run). screen/gap/review copy their CSV into docs/ themselves; all daily workflows
  retry their push 5x (an app run once lost the push race to dip and left the app on old picks).
- news_events.py + news_more.py: NSE + BSE announcements (BSE needs cookie warm-up; NSE/BSE dupes merged within 20 min),
  Google News per stock (docs/stock_news.json), ET/BS/Moneycontrol/Mint RSS; locked stocks included; EVENT_UNKNOWN flag
  when the result-date lookup fails (checklist shows '?', never a false pass).
- Studies (manual workflow_dispatch): dip_enh, dipstudy, dip_validate, backtest, sweep, signals, events, filters,
  orb (Angel 15-min), momdip, trendline. Results in out/*_summary.txt.
- Scheduled tasks (Claude): morning shortlist 8:12 IST and gap-check 9:41 IST.

## Strategy facts (do not oversell)
- Breakout/pullback picks have no backtested edge. Dip-in-uptrend is the one verified setup: avgR ~+0.12 to +0.2,
  ~60% win, ~2 signals/week, 2025 ~0. Tier A (3d drop <= -8%) is stable; Tier B weaker. Dip A+ = Tier A + RVOL<1 + ADX>=25
  (hint only: n=253, +0.22R). Entry next open ~9:20, stop 2 ATR, max 5 days. Skip if gap >+1.5% or < -3%.
- Forward test: log 30-50 small trades as DIP-A / DIP-A+ / DIP-B in the Picks sheet reason column.
- Filters tested and rejected: candle patterns (twice: dip_enh and momdip reversal candle overfit), Fibonacci, MACD,
  SMA200. Hold 10d is not stable (2025 negative).
- Out-of-sample (2025-26) numbers are what the app quotes: Tier A ~+0.09R, A+ ~+0.15R, Tier B ~0R.
- momdip (2026-10-17): only the sharp 3-day dip zone works; EMA20/EMA50 touch, 10% off high, breakout retest do not.
  60-day return top 20% ("Momentum") + dip: test +0.04R vs plain dip +0.02R -> shown only as a 'Momentum' tag
  (dip_scan.py MOM60_TOP20 column), not a rule.
- Intraday ORB 15-min + 8 EMA (an Instagram reel): 213 F&O stocks, 1 year: ~0R before costs, -0.2 to -0.35R after 0.15%
  costs; 0 of 32 combos positive. Do not add intraday setups; costs kill tight stops.
- Trendline break (>=3 pivots, owner's reel, long+short, sweep/trend filters, 2-4R): 0 of 48 combos positive in both
  train and test. Long test -0.09 to -0.19R (random -0.15R). Short test slightly plus only because 2025-26 was weak (train
  negative). Not added.
- R:R rule in app: picks without room for 1:2 before the next 20/60-day/52-week high get an 'R:R kam' chip and -12 rank
  (not backtested; targets themselves stay realistic, since 2R targets did not help in the sweep backtest).
- Owner wants 2-3 setups side by side, each labelled with its strategy + backtest status, and the daily move (ATR) shown.
  Shorts: cash market allows intraday only; 2-5 day shorts need futures (too big for Rs 50k) or options (he avoids).

## Data rules
- Analysis (EMA/RSI/ATR/trend/picks/Dip) uses the previous close (bhavcopy appears ~6 PM IST). Only prices/gap/SL are live.
- NSE and Yahoo are blocked from Claude's sandbox but work from GitHub Actions. raw.githubusercontent.com is readable.
- Alerts are rule-based, not backtested. Macro dates in docs/macro.json: RBI, India CPI, Budget need verifying.

## App notes (2026-10-17)
- Plan tiles open list pages; floating "AI se poocho" on stock detail opens claude.ai/new?q=<context prompt> (no API key;
  owner declined an in-app paid API chat). Ignore list = watchlist rows grouped by reason with the numbers behind each
  (ASM type LT/ST from restrict.py + how far it ran, circuit as info only). Quality screen is a PASS/FAIL table.
- Pre-trade checklist is fully automatic (no manual ticks except optional fundamentals). Logged trades are checked
  against the app's trigger (picks_review.py entry_check: OK / EARLY / CHASED).

## Known open items
- docs/picks_review.csv scorecard: picks_review.py now handles DIP rows (market entry next open).
- Dip stocks are not in angel_gap.py, but live alerts (watch_alerts.py) cover the Dip gap rule.
- Morning scheduled prompt could mention restrict/ASM, A+ and IGNORE rules.
- Offered, not built: bulk/block deal + insider buying chip on picks.

## Market regime (regime_study.py, regime.yml har Shanivar)
- Regime = liquid stocks (20-din turnover 5cr+) me kitne % EMA50 ke upar: STRONG 60+, MIXED 40-60, WEAK 25-40, VWEAK <25.
- Result (SL 2ATR, max 5 din, 0.25% cost): WEAK me Dip A +0.15R (59% jeet, 4/5 saal); VWEAK me Oversold bounce +0.26R (67%, 5/5) aur Gehra oversold +0.16R (5/5);
  MIXED me koi setup pakka nahi; Breakout har haal me minus.
- App: Picks par "Aaj ka market" card (docs/regime.json + docs/regime_today.json), Breakout/Pullback/Dip strategy line par
  "Is market me chala / nahi chalta" chip, Oversold bounce cards sirf VWEAK me (warna ek line).
- dip_scan.py roz: BOUNCE/DEEP rows dip_latest.csv me (app inhe Dip list se alag rakhta hai) + docs/regime_today.json.

## Live setup study (intraswing_study.py, Actions > intraswing, manual)
- 15-min Angel data (F&O 213 stocks, Jan-Oct 2026, ~176 test din). Breakout / reversal / Dip A / bounce din me pakad ke 3:15 entry vs kal open.
- Result 2026-10-17: koi setup PASS nahi. Breakout har haal me minus (-0.04 se -0.55R). Reversal minus. Bounce 3:15 VWEAK +0.13R
  par doosre aadhe me -0.18R (fail). 3:15 entry aksar kal-open se thoda kam bura (gap ka nuksan bachta hai) par dono minus.
- Faisla: live "trade layak" highlighter nahi banaya. Data kam hai: data_orb cache badhta nahi (fetch_all purani file skip karta hai).
- data15.yml (har Ravivar): orb_study.fetch_all ab incremental hai (purani file me sirf naye din). data_orb cache + backup
  branch "data-15min" (tar.gz, 90MB parts, har baar force-push single commit). Mahine ke pehle hafte intraswing study dobara chalti hai.

## Market structure setup (reel "retracement -> expansion", regime_study STRUCT/STRUCT_DEEP)
- Fractal swing (2 din dono taraf), HH+HL, 38%+ retracement jo pichhla HL na tode, aaj close retracement ke chhote high ke upar.
- 4 saal: STRONG/MIXED/WEAK me minus (-0.02 se -0.42R); VWEAK me +0.19 se +0.37R (SL swing low, 2R, 10 din: +0.32R, 57%, 3/3 saal, n~250, clustered).
- dip_scan.py roz STRUCT/STRUCT_DEEP rows (STOP_REF = swing low*0.998, TARGET_REF 2R) likhta hai; logic regime_study.struct_sig jaisa (dono saath badlo).
  App: structSection cards sirf VWEAK, warna ek line. watch_alerts: Structure SL = STOP_REF, sirf VWEAK me.

## Purani reels dobara (awaaz sun ke, 2026-10-17)
- ORB reel ki awaaz: 9:25 par 1.5-2% upar/neeche wale 3-4 F&O stock, advance/decline se disha, target 1:3 -> orb_study VIDEO + AD930 + 3R:
  kharche ke baad -0.17 se -0.33R (fail). SL ~0.7% hone se 0.15% kharcha hi ~0.2R kha jaata hai.
- Trendline reel ki awaaz: "4th-5th touch par tootti hai", liquidity fake-out -> T4 / T4+SWEEP: best LONG T4+SWEEP ~0R
  (base -0.07R se behtar) par 2025+ test me minus; koi combo train+test dono me plus nahi (0/72). Reel ka asli timeframe 3-5 min intraday.
- Awaaz: pip install faster-whisper, model 'medium', audio 25 sec tukdon me (vad_filter, beam 1) -> ~7 min per 2 min video.

## Demand zone + CHoCH reel (regime_study DEMAND_CHOCH) aur "har stock ki apni strategy" (stock_study.py, Actions > stockfit)
- DEMAND_CHOCH: bahut kam banta hai (~360 trade/4 saal). STRONG -0.02..-0.06R, MIXED -0.11..-0.20R, WEAK +0.20..+0.40R par sirf 51 trade (pass nahi).
- stock_study (top 50 ATR% liquid stock, setup 2022-24 se chuna, 2025-26 pe check): apni strategy -0.03R, random setup -0.14R,
  sab signal -0.10R, Dip A +0.04R. TRAIN vs TEST rank correlation +0.07; TRAIN ke top 20% jode +0.38R -> TEST -0.14R. Faisla: per-stock fitting kaam nahi karta.
- stock_study PICK=turnover (50 sabse bade stock): apni strategy -0.18R, random -0.18R, sab signal -0.15R; TRAIN top 20% +0.33R -> TEST -0.15R,
  correlation +0.12; sirf 11/40 stock TEST me plus (TCS PULLBACK +0.42 -> -0.69). Bade stocks me bhi per-stock fitting fail.
- 2025 se seekho, 2026 pe lagao (MIN_TRAIN 4): chhote stock apni strategy -0.26R (random -0.07R), bade stock -0.27R (random -0.24R);
  TRAIN top 20% +0.44/+0.37R -> TEST -0.01/-0.37R. Mandi-se-mandi tulna me bhi per-stock pattern nahi tikta.

## 20 indicators / platform signals (indicators.py, regime_study me, 2026-10-18)
- MACD, RSI30, Supertrend, Bollinger, golden cross, EMA9/21, stochastic, ADX, Donchian, NR7, gap&go, delivery surge,
  TradingView-jaisa Strong Buy, Ichimoku, PSAR, CCI, Williams, Heikin-Ashi, vol dry-up: STRONG/MIXED/WEAK me koi bhi
  random liquid stock (base) se pakka behtar nahi (TV Strong Buy har haal me base ke barabar ya neeche).
- VWEAK me base khud +0.06R (2ATR/5d) / +0.14R (1.5ATR/10d/T2R): bahut kamzor market me lagbhag kuch bhi kharido to plus.
  Base se kaafi upar sirf: OVERSOLD_BOUNCE (+0.26 vs +0.06), STRUCT_DEEP (+0.37 vs +0.14). WEAK me DIP_A (+0.15 vs -0.22).
- App card: core setups + sirf wo indicator jo base se 0.05R+ upar (table me baseR); random stock ka base bhi dikhaya.

## Live upgrade (2026-10-18): live breadth, 3:15 taiyari, trade live P&L
- dip_scan.py roz docs/live_base.json likhta hai (har liquid stock: e20, e50, e50 10 din pehle, c3/c60/c10, RSI au/ad, close, atr).
- live_scan.py: breadth(items, base) aur prep(items, base) - dip_scan jaisi definitions (synthetic test: breadth, Dip A, bounce 100% match).
- live.py: har 5 min base ke ~1100 stock ka quote (50 ke batch) -> live['breadth'] {pct, regime, at, hist, base_*};
  14:30 se live['prep'] {dip, bounce}; 15:12 ke baad ek baar Telegram "3:15 TAIYARI". Picks sheet (gviz) ke trade symbols bhi live list me.
  Payload 44000 char se upar ho to purane alerts kat-te hain (Apps Script limit 45000).
- App: plan card me "Live market" line (#lvbr), "Kal ke liye taiyari" card (#lvprep), Trades tab me live P&L (data-tpl) + total (#tplsum).
- Regime card ki har setup line dabao -> docs/regime_trades.json (regime_study, 2ATR/5d): us market haal me sabse zyada
  bane 12 stock (trade, jeet, avg R) + haal ke 30 trades (signal din, stock, R). Har Shanivar update.

## App design v2 (2026-10-18)
- Part 1: Inter font, header logo + "⋯" menu (Theme/Alerts/Install), icon tab bar (News badge .nbd), ₹, Hinglish trade status (STL),
  lambe text 2 line clamp (clampLong via MutationObserver on #v; .r/.ign/.tiles/.ir chhodta hai).
- Part 2: watchlist rows: pickRow / dipRow / pinRow + wlist(); live cells data-lvq (pxq) aur data-lvs (lstat) paintLive me.
- Part 3: stock page chart: candles.py (app.yml, kaam ke max 160 stock x 100 din -> docs/candles.json), lightweight-charts 4.1.3
  (jsdelivr, lazy). EMA20/50, volume, entry/SL/target price lines (logged trade ho to uske). Baaki stocks: TradingView link.
- Chart live: chLive() aaj ki candle LV.items se update karta hai (paintLive har ~30 sec), "LIVE" dot. Markers: signal din (setup naam),
  logged trade ki entry. "ⓘ Ye trade kyun?" (whyHtml): setup rule (SETRULE), rk.P/rk.N, dip hisaab, regChip, plan kaise bana.
- candles.py: ek din ki do bhavcopy file (NSE re-upload) ab ek hi candle; app bhi duplicate/zero rows hata deta hai.
- Live intraday chart: live.py har 2 min chart stocks (candles.json + pins + sheet trades, max 60) ke aaj ke ONE_MINUTE candles
  GitHub 'live-data' branch par intra/SYM.json likhta hai (har baar ek orphan commit force-push; live.yml contents: write).
  App raw.githubusercontent.com/<repo>/live-data/intra/SYM.json padhta hai. 1m/5m/15m/1H = intraday.json (shaam ke 15-min,
  ~5 din) + aaj ke 1-min, har 30 sec refresh (market time). Apps Script me koi badlav nahi chahiye.

## SIBE reel (Sweep -> Break of structure -> Entry) — FAIL (2026-10-19)
- Rule from the reel audio: mark previous session high/low; price sweeps one, then BOS the other way -> entry; SL beyond sweep; TP = opposite swing.
- Test: sibe_study.py on data_orb (213 F&O stocks, 15-min, 2025-12-29..2026-10-16). Sweep of the previous day's low/high, close back beyond it + beyond the last-3-bar extreme, entry next open (by 14:30), SL sweep extreme ±0.05%, target previous-day opposite extreme or 2R, EOD exit, 0.15% cost.
- Synthetic random walk: gross ~0 (method clean).
- Real: ~26k trades, ALL long -0.16R, short -0.10R net; gross ~0. No regime/side passes (WEAK short 2R +0.008 with second half -0.16). Not added to the app.
- Workflow: sibe.yml (manual). Output out/sibe_summary.txt.

## New listings (first 60 days) — ipo_study.py (2026-10-19)
- User idea: a new listing sitting at its post-listing low "can't fall further" -> buy. Tested days 5-59 after listing, 1294 listings 2022-09..2026-10, ATR floored at 2%, next-open entry, 0.25% cost.
- His idea FAILS: NEAR_LOW (0-3% above post-listing low) -0.10R, REV_LOW (bounce candle off the low) -0.08R, BELOW_LIST (15%+ under listing open) -0.07R. Base (any new-listing day) -0.06R.
- What worked (2ATR stop / 5-day exit): DROP8 (3-day fall >= 8%) +0.057R ALL, 4/4 years, +0.8% avg; VWEAK +0.12R (n 315), STRONG +0.12R (n 153), MIXED negative. NEW_LOW (close below post-listing low) VWEAK +0.17R (n 266), ALL only +0.035.
- App section "Naye listing ka dip" (dip_scan TIER NEWDROP, EQ+BE, 2ATR SL, half qty; MIXED regime shows "trade nahi"). Fundamentals/news for IPOs not testable (no history).
- App: stocks with 5-59 days now show a lite page (stock_report lite()).
- News: news_all.py maps ~1,900 headlines/run from 15 RSS feeds + 29 Google News market searches to all stocks; News tab split into Telegram (headings, tap to open) and Baaki news.

## IPO tab + backtest (2026-10-19)
- ipo.py (news.yml, every 20 min): ipowatch GMP + detail, chittorgarh year-wise financials/borrowing, NSE live subscription, NSE RHP (zip, pypdfium2) cash & bank (unit-checked vs net worth). Two verdicts: Listing (QIB+GMP) and Company (profit/growth/ROE/PE/OFS/net cash).
- ipo_backtest.py (ipobt.yml, manual; cache out/ipo_hist.json): 423 IPOs 2023-04..2026-10 matched to NSE listing-day prices.
  Mainboard (216): APPLY 88 -> avg +34.5%, 95% positive; SOCH 46 -> +9.2%, 80%; SKIP 82 -> -2.9%, 34%. QIB 50x+ +32% (93%); QIB 1-10x -1.4%.
  SME (207): APPLY +48.6% (95%); SKIP 0.0% (45%). Holds every year 2024/25/26. GMP 25%+ is ~accurate on average; GMP <10% overstates by 2-4%.
  Caveat: uses final-day QIB and last pre-listing GMP (slightly after the bid deadline). Company verdict NOT validated (old IPOs mostly lack financial data).
- App shows the track record on every IPO card (docs/ipo_backtest.json).
- Paper trading: paper.py (dip.yml) auto-tracks all signals -> docs/paper.json; manual paper trades in localStorage (Trades > Paper > Mere trade).
- UI: Picks sub-tabs (Trade/Setups/Savdhani/Market/Locked), market gauge + intraday sparkline, alerts page via header bell, live setups card (prep from 09:20).

## Z-score mean reversion reel (2026-10-20) - only VWEAK, not added
- zscore_study.py (zscore.yml): 20-day z <= -2, next-open entry, exit at the 20-day average, SL/time stop; 3235 stocks 2022-09..2026-10.
- ALL regimes ~0 (Z-2/SL2ATR/10d -0.03R; random-day base -0.18R). WEAK -0.10R, MIXED -0.09R. VWEAK passes: no-SL/10d +0.16R (3/3 yrs),
  SL3ATR/20d +0.11R (75% win, 3/3), Z-2.5/SL2ATR +0.16R. Synthetic: ~0 with 54-67% "win rate" (small target inflates win %).
- Same regime as OVERSOLD_BOUNCE (+0.26R VWEAK) and largely the same stocks, so no new app section.

## MA crossover reel (9/21, SL1%/T2%) - FAIL (2026-10-21)
- ma_study.py (ma.yml). Nifty 2008-2026 (Yahoo): reel version 125 trades, 36% win, CAGR -0.4%, last 2 yrs -9%; 9/21 cross-only +4.0% CAGR,
  EMA +6.8%, buy&hold +7.3% (DD -60% vs -20/-25%). Stocks 2022-26 (21.8k trades): SL1/T2 -0.49%/trade, 25% win, 0/5 years plus;
  cross-down exit +0.72% vs random in-trend entry +0.80% (signal adds nothing). Not added.
- Also: Angel scrip master breaks mid-download (2026-10-21) -> live.master_list() resumes via Range; docs/angel_tokens.json cache.
- New VWEAK setup DROP10 ("ek din me 10% gira", zscore_study +0.33R) in dip_scan/app/paper/live prep.

## Results trading (LTTS case, 2026-10-21)
- Result timestamps: NSE corporate-announcements "Outcome of Board Meeting" (cache out/results_dates.json). Good coverage only 2025+
  (~6k/yr; 2022-24 ~500/yr), so all three studies are effectively 2 years.
- revbo_study.py (revbo.yml) - reversal breakout (20d-high + vol, EMA20<=EMA50, LTTS 14-Oct): FAIL. 3895 trades, 5/10/20d
  -0.88/-1.09/-1.14% vs random -0.37/-0.22/-0.29%; +4% vol3x version same. Current BO_UP rule ~= random (-0.51/-0.34/-0.04%). Keep EMA20>EMA50.
- results_study.py (results.yml) - post-result trade: next-day OPEN entry FAILS (UP4+VOL3 -0.52/-0.37/-0.03%). Buying a bad
  result (-4%, vol3x) worst (-1.5..-1.7%). Reaction-day CLOSE entry tentative plus: UP8+VOL3 +0.64/+0.70/+1.44% (n 338),
  GAP3 held (close>=open) +0.41/+0.64/+1.65% (n 334); random -0.14/-0.22/-0.08%. Mostly STRONG regime, ~0 in MIXED, 2 yrs only. Not added.
- preres_study.py (preres.yml) - predict before the result (buy 3d before, exit 2d after): FAIL. No signal predicts the result
  day: all results 42% up; PREV_GOOD 42%; SEASON_GOOD 43%; DELIV_UP 34%; SCORE3+ 31% (-1.35%/trade). VWEAK plus rows (+2%)
  match the VWEAK random base, not prediction. Not added.

## Liquidity + candlestick reel (2026-10-21) - FAIL
- liqc_study.py (liqc.yml). Daily version (reel uses 5m/1H; no intraday history): first break of the prior 20-day low, candle type
  on that day, next-open entry, SL under the sweep low, 2R/10d or 5d exit. 3235 stocks 2022-09..2026-10.
- Every type is negative overall: REJECT (closed back above) -0.20R (14.6k), HAMMER -0.27R, BULL -0.12R, RAN -0.30R; equal lows no help.
  Only BULL + equal lows in VWEAK +0.16R (n 315, 4/4 yrs), weaker than OVERSOLD_BOUNCE/STRUCT/DROP10 in the same regime. Not added.
- Paper trading also tracks watch-only result-day setups RES_GAP / RES_UP8 (go=False, excluded from ALL stats).
- Gap check writes a date column; the app shows only today's check (stale holiday NO_DATA fixed), API_BUSY on Angel rate limit.

## SMC "Power of 3" reel (AMD: open ke neeche jaal -> MSS -> FVG entry) - FAIL (2026-10-21)
- po3_study.py, run locally on the 15-min backup (branch data-15min -> data_orb/): 214 F&O stocks, 2025-10-13..2026-10-16.
- Long: MSS entry 17.5k trades -0.01R before costs, -0.13R after 0.15%; FVG retrace 3.1k -> +0.01R / -0.16R; 0/13 months plus.
  Short mirror ~+0.02R / -0.10R. Random-time base ~0R / -0.2..-0.3R. Synthetic random walk gives the same ~0R. Not added (and intraday).

## Long build-up / futures OI (order-block.com reel, 2026-10-26) - FAIL (one lead)
- oibu_study.py (oibu.yml; OI from NSE F&O bhavcopy, old + UDiFF formats, non-expiring contracts only; cache out/fo_oi.json in
  Actions cache). 2022-09..2026-10, 1011 days, next-open entry, SL 2 ATR, 0.25% cost.
- LONG_BU (price +2%, OI +5%) 5d -0.11% (n 3939) vs price-only +2% -0.19% vs random -0.31%: OI adds ~nothing. TOP5 worse (-0.40%).
  STRONG version +0.05%. Short covering -0.17%, short build-up -0.49%.
- Lead (not added): LONG_UNWIND (price -2%, OI -5% = longs exiting) as a buy: 5d +0.45% (54% win, 4/5 yrs, n 878), 10d +0.57%;
  STRONG +0.65%, VWEAK +1.45% (n 197) but MIXED/WEAK negative. Needs a threshold robustness check before any use.
- unwind_study.py (unwind.yml) robustness check of LONG_UNWIND: NOT robust, not added. Grid looks good (P-3 OI-3 5d +1.11%,
  P-5 OI-3 +2.63% n 180) but P-2 OI-5 is +1.06% in the 1st half (2022-09..2024-10) and -0.66% in the 2nd half (recent 2 yrs),
  and the gain sits in the expiry week (day>=22 +0.68%) vs other days -0.03%. Price-only P-2 -0.13%. Re-check later with more data.

## Paper week 19-23 Oct 2026 and the fix (2026-10-26)
- Paper: 43 closed, 2 wins, -40R. Breadth fell 22% -> 11%; 23 Oct a market-wide sell wave (Nifty low 12:50, most stock lows
  10:15-11:10) took stops 0-1.5% below; 15/23 back above stop by 26 Oct, only 3 above entry. No code bug (backtest engine agrees).
- turn_study.py: VWEAK bounce works while breadth still falls (+0.25R); "turning" days are worse (+0.06R). No week like 19-23 Oct in 4 yrs.
- pick_study.py (4 yrs, 3966 signals): close-basis 2-ATR stop >= intraday stop in every setup (all +0.22R -> +0.25R; STRUCT_DEEP
  +0.31 -> +0.45R). Top-2-per-day by any rule ~= random 2 (+0.03..+0.09R) vs all signals +0.22R: the edge is in days with many
  signals. Random 2 per day by signals that day: 1-5 -0.07R, 6-15 +0.02R, 16-40 +0.24R, 41-100 +0.17R, 100+ +0.83R.
- Changes: paper.py go for BOUNCE/DEEP/STRUCT*/DROP10 only if VWEAK and day_count() >= 16 (unique liquid symbols, TURN20 >= 5 cr);
  stop_mode 'close' for those + A (new and waiting signals). App: bigDay() gates those sections ("aaj trade nahi" on small days),
  "bada din" note, SL close-par text.

## Top gainers reel (Nifty 50 top % gainers at 3:20 -> next 4-5 days, 2026-10-26) - mixed, not added
- topgain_study.py (run locally on 4 yrs bhav; out/topgain_summary.txt). Universe = top 50 by 60-day turnover (no historical Nifty list).
- Buy at that day's CLOSE: TOP3 5d +0.27% vs all 50 -0.01%, bottom-3 -0.15%; TOP3 with +2%: +0.32% (2/5 yrs).
  Buy next OPEN: TOP3 -0.26% vs all -0.19% -> the whole edge is the overnight gap; the reel's 3:20 entry matters.
- By regime (close, 5d, TOP3 +2%): STRONG +0.67% (4/4 yrs), WEAK +1.40% (4/4), MIXED -0.77%, VWEAK -0.17%. Inconsistent -> watch only.

## "ACE jaisa" support bounce (2026-10-27) - FAIL, not added
- supp_study.py (run locally, out/supp_summary.txt): 15%+ below 60-day high, low within -2%/+3% of 2+ prior swing lows (6 months),
  TOUCH (next open) or CONFIRM (close > previous high within 5 days), SL zone low - 0.5 ATR. Synthetic: ~0/slightly minus.
- All variants negative overall (TOUCH -0.13R n 21.5k, CONFIRM -0.12R, +uptrend/+RSI<35/+3 touch similar). Only VWEAK slightly plus
  (+0.07..+0.19R) = same as the VWEAK random base (+0.16R), weaker than OVERSOLD_BOUNCE. Support level adds nothing.
