name: backtest
on:
  workflow_dispatch: {}
permissions:
  contents: write
jobs:
  backtest:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Download 1 year bhavcopy
        run: python fetch.py
        env:
          DAYS: "380"
      - name: Run backtest
        run: python backtest.py data out
      - name: Commit result
        run: |
          git config user.name "swing-bot"
          git config user.email "swing-bot@users.noreply.github.com"
          git add out/backtest_summary.txt out/backtest_trades.csv
          git diff --cached --quiet || git commit -m "backtest $(date -u +%F)"
          git push
