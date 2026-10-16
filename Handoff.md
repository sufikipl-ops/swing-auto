# Handoff — swing-auto (Swing Desk)

State as of 2026-10-16. Read this first before changing anything.

## What this is

An NSE swing-trading helper that runs entirely on GitHub Actions (no server):

1. **Daily data**: downloads NSE bhavcopy files (`fetch.py`) and builds the screens.
2. **Swing Desk app**: a PWA on GitHub Pages (`docs/index.html`, `sw.js`, `manifest.webmanifest`) that reads the JSON/CSV files in `docs/`.
3. **Live feed + alerts**: during market hours `live.py` polls Angel One SmartAPI every ~25 s, pushes prices to a Google Apps Script backend, and sends Telegram "IGNORE" alerts (`watch_alerts.py`) through that backend.
4. **Research scripts**: backtests and studies on bhavcopy history. Their results live in `out/*_summary.txt`.

The repo must stay **public** (GitHub Pages). Never commit secrets.

## Scripts

| Script | Purpose | Output |
|---|---|---|
| `fetch.py` | NSE bhavcopy downloader (`DAYS` env, default 100) | `data/` (not committed) |
| `screen.py` | BREAKOUT / PULLBACK candidates | `out/screen_latest.csv`, `out/screen_YYYYMMDD.csv` |
| `dip_scan.py` | DIP setup (the only backtested edge, see below) | `out/` + `docs/dip_latest.csv` |
| `stock_report.py` | Per-stock EMAs, levels, score and buy zone for every NSE EQ stock | `docs/stocks.json` |
| `news_events.py` | NSE announcements + RSS headlines for candidates; optional AI summary via `ANTHROPIC_API_KEY` | `out/news_events.*`, `docs/announcements.json` |
| `restrict.py` | ASM/GSM, circuit band, series (BE/T2T) checks | `docs/restrict.json` |
| `global_mkt.py` | Global indices, commodities, FX, headlines and mood (Yahoo) | `docs/global.json` |
| `names.py` | SYMBOL → company name map (NSE EQUITY_L) | `docs/names.json` |
| `angel_gap.py` | Morning gap-check vs the last screen's triggers (Angel 15-min candles) | `out/gap_check.*` |
| `angel_test.py` | Angel One login / API smoke test | `out/angel_test.txt` |
| `live.py` | Live LTP feed to the Apps Script backend, plus alerts; `TEST_ALERT=1` sends one test Telegram message | none (pushes to Sheet) |
| `watch_alerts.py` | Alert rules called by `live.py` each cycle (same rules as the app) | Telegram via backend |
| `picks_review.py` | Forward test of picks logged in the Google Sheet "Picks" tab | `out/picks_review.*` |
| `backtest.py`, `sweep.py`, `filters.py`, `signals.py`, `events.py`, `dip_study.py`, `dip_enh.py` | Research only (manual `workflow_dispatch`) | `out/*_summary.txt`, `out/*_results.csv` |

## Schedules (cron is UTC; IST = UTC+5:30, Mon–Fri)

| Workflow | IST time |
|---|---|
| `news` | 07:00, then every 20 min 08:30–16:30 |
| `global` | 08:30, every 30 min 09:30–16:30, 22:00 |
| `restrict` | 08:40 and 19:10 |
| `gap` | 09:20 |
| `live` | 09:10–15:05 and 14:55–15:32 (two jobs because of the 6 h job limit) |
| `daily-screen` | 18:00 (retry 19:30 if NSE is late) |
| `dip` | 18:20 (retry 19:50; fails on purpose if today's file is missing) |
| `app` (stocks.json) | 18:20 |
| `review` | 21:00 |
| `names` | monthly, 1st at 08:00 |

Data workflows commit their own results back to `main` (e.g. commits named `screen 2026-10-16`, `dip ...`, `news ...`). Expect frequent bot commits; pull before pushing.

## Secrets (GitHub → Settings → Secrets → Actions)

- `ANGEL_API_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_PIN`, `ANGEL_TOTP_SECRET` — used by `live`, `gap`, `angel_test`.
- `ANTHROPIC_API_KEY` (optional) — `news`. Model is set by `ANTHROPIC_MODEL` and defaults to `claude-haiku-4-5`.

The Apps Script backend URL and key (`PIN_URL`, `PIN_KEY`) are hard-coded in `docs/index.html:105`, and `live.py` reads them from there (`page_config()`). This makes them public, so the backend should treat that key only as a light gate, not real auth. The Telegram bot token lives in the Apps Script, not here. `picks_review.py` reads the Sheet's public gviz CSV export.

## Research findings (short version)

- **Breakout/pullback screen (`screen.py`) has no edge.** 1-year backtest: 9,774 signals, win 40%, avgR −0.12, PF 0.74. No filter tried (ADX, MACD, Nifty trend, delivery flags) made it positive. Treat screen picks as a watchlist, not signals.
- **DIP in uptrend is the only setup that holds up.** 4 years of liquid stocks; next-open entry, 2 ATR stop, exit at day-5 close, 0.25% cost:
  - Tier A (3-day drop ≤ −8%, U2 trend): n=475, win 61%, avgR +0.165, PF 1.99, positive every year (2025 roughly flat at +0.01).
  - Tier A+B base: n=922, avgR 0.130. Best add-on filters (`dip_enh`): close in lower quarter of the day's range, ADX≥25, close below lower BB, RVOL<1. Pairs reach avgR ~0.20. Many filters were tried, so treat these as hints. They feed the "Dip A+" tag.
- Forward test (`out/picks_review.txt`, 2026-10-15): 4 picks, 0 closed. Far too early to judge; aim for 30–50 closed trades first.

## Recent changes (PRs #1–#3, 2026-10-16)

- #1 Live IGNORE alerts (`watch_alerts.py`), Dip A+ tag, more frequent news/global runs.
- #2 Bad-news regex ignores NSE's licence-category label containing "suspension" (`NEUTRAL_CAT`; fixed an ATHERENERG false positive).
- #3 `live` workflow got a `test_alert` input: run it manually to send one TEST Telegram alert outside market hours.
- After that, `docs/index.html` was edited directly on `main` (commit `3e3eef9`).

## Known issues / loose ends

- **Angel rate limit**: `angel_test` on 2026-10-16 logged in, but 2 of 3 candle calls returned HTTP 403 "exceeding access rate". Keep request pacing in `live.py` / `angel_gap.py` conservative.
- `github/workflows/sweep.yml` (no leading dot) is a stray duplicate of `.github/workflows/sweep.yml` and never runs. It is safe to delete.
- Branch `claude/lucid-cerf-clsg0w` is behind `main` (older `index.html`) and has nothing unmerged worth keeping.
- Many commits were "Add files via upload" from the GitHub web UI, so check `git log -p` when something changes unexpectedly.
- Comments and UI text are in Hinglish; keep that style when editing.

## How to work on it

- Run locally: `python fetch.py && python screen.py data out` (standard library only, Python 3.12).
- `live.py` needs the Angel secrets in env and only runs during IST market hours unless `TEST_ALERT=1`.
- Alert rules exist in **two places** (`watch_alerts.py` and the JS in `docs/index.html`); change both together.
- Not financial advice; all results are backtests with the stated cost and fill assumptions.
