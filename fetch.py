# Downloads NSE full bhavcopy files (last ~100 calendar days) into ./data, skipping holidays/missing days.
import datetime, os, sys, time, urllib.request
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HDR = {"User-Agent": UA, "Referer": "https://www.nseindia.com/",
       "Accept": "text/csv,*/*", "Accept-Language": "en-US,en;q=0.9"}
os.makedirs("data", exist_ok=True)
today = datetime.date.today()
got = miss = fail = 0
for back in range(0, int(os.environ.get("DAYS", "100"))):
    d = today - datetime.timedelta(days=back)
    if d.weekday() >= 5:
        continue
    name = "sec_bhavdata_full_%s.csv" % d.strftime("%d%m%Y")
    path = os.path.join("data", name)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        continue
    url = "https://nsearchives.nseindia.com/products/content/" + name
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read()
        if len(body) > 1000:
            open(path, "wb").write(body); got += 1
        else:
            miss += 1
    except urllib.error.HTTPError as e:
        if e.code == 404: miss += 1      # holiday / not published yet
        else: fail += 1; print("HTTP", e.code, name)
    except Exception as e:
        fail += 1; print("ERR", name, e)
    time.sleep(0.6)
print("downloaded", got, "missing/holiday", miss, "errors", fail)
if got == 0 and not any(f.startswith("sec_bhavdata_full_") for f in os.listdir("data")):
    print("NO DATA - NSE may be blocking this server"); sys.exit(1)
