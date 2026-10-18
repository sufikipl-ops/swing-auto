// Swing Desk: live intraday candles. live.py (GitHub) har ~2 min me bhejta hai, app chart padhta hai.
// Har stock ek row (sheet "Intra"): Symbol | Updated | JSON {date, bars:[[hhmm,o,h,l,c,v],...]}
function ix_sheet_() { return pa_sheet_('Intra', ['Symbol', 'Updated', 'JSON']); }

function ix_put_(body) {
  var data = body.data || {}, date = String(body.date || '');
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = ix_sheet_(), n = sh.getLastRow();
    var rows = n >= 2 ? sh.getRange(2, 1, n - 1, 3).getValues() : [];
    var pos = {};
    rows.forEach(function (r, i) { pos[String(r[0])] = i; });
    var now = new Date(), cnt = 0;
    Object.keys(data).forEach(function (sym) {
      var s = String(sym).toUpperCase().replace(/[^A-Z0-9&\-]/g, '').slice(0, 20);
      var js = JSON.stringify({ date: date, bars: data[sym] });
      if (!s || js.length > 48000) return;
      if (pos.hasOwnProperty(s)) rows[pos[s]] = [s, now, js];
      else { pos[s] = rows.length; rows.push([s, now, js]); }
      cnt++;
    });
    if (rows.length) sh.getRange(2, 1, rows.length, 3).setValues(rows);
    return { ok: true, n: cnt };
  } finally {
    lock.releaseLock();
  }
}

function ix_get_(p) {
  var sym = String(p.sym || '').toUpperCase().replace(/[^A-Z0-9&\-]/g, '').slice(0, 20);
  var sh = ix_sheet_(), n = sh.getLastRow();
  if (n < 2 || !sym) return { ok: true, sym: sym, bars: [] };
  var v = sh.getRange(2, 1, n - 1, 3).getValues();
  for (var i = 0; i < v.length; i++) {
    if (String(v[i][0]) === sym) {
      try { var d = JSON.parse(v[i][2]); return { ok: true, sym: sym, date: d.date, bars: d.bars || [] }; } catch (e) {}
    }
  }
  return { ok: true, sym: sym, bars: [] };
}
