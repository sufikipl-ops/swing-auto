// Swing Desk: GitHub ke late/skip schedule ka ilaaj. Google Apps Script ka timer har 5 min chalta hai aur sahi waqt par
// GitHub workflow khud chalu karta hai (workflow_dispatch). Isse live feed roz ~9:08 tak shuru ho jaata hai.
// Setup (ek baar):
//   1) Project Settings (gear) > Script Properties > GH_TOKEN = GitHub fine-grained token (sirf swing-auto, Actions: Read and write)
//   2) Ye file paste karke Save, phir upar se function "setupTimer" chuno aur Run (Google permission maangega: Allow)
// Token kabhi chat/screenshot/GitHub me mat daalna, sirf Script Properties me.

var GH_REPO = 'sufikipl-ops/swing-auto';
// [workflow file, IST se, IST tak]: is khidki me din me ek hi baar chalu hoga
var KICKS = [
  ['live.yml', '09:05', '09:40'],   // subah live feed
  ['gap.yml', '09:22', '09:50'],    // 9:20 gap check
  ['live.yml', '14:50', '15:10']    // GitHub ki 6 ghante ki limit ke baad 3:32 tak live (pehla run khatam hote hi chalega)
];

function kickWorkflows() {
  var now = new Date();
  var dow = Number(Utilities.formatDate(now, 'Asia/Kolkata', 'u'));   // 1=Mon .. 7=Sun
  if (dow > 5) return;
  var day = Utilities.formatDate(now, 'Asia/Kolkata', 'yyyy-MM-dd');
  var hm = Utilities.formatDate(now, 'Asia/Kolkata', 'HH:mm');
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('GH_TOKEN');
  if (!token) { console.log('GH_TOKEN nahi mila (Script Properties me daalo)'); return; }
  KICKS.forEach(function (k) {
    if (hm < k[1] || hm > k[2]) return;
    var flag = 'kick_' + day + '_' + k[0] + '_' + k[1];
    if (props.getProperty(flag)) return;
    var res = UrlFetchApp.fetch('https://api.github.com/repos/' + GH_REPO + '/actions/workflows/' + k[0] + '/dispatches', {
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
      payload: JSON.stringify({ ref: 'main' })
    });
    var code = res.getResponseCode();
    console.log(hm + ' ' + k[0] + ' -> ' + code + ' ' + res.getContentText().slice(0, 200));
    if (code == 204) props.setProperty(flag, '1');
  });
  // purane flag saaf (7 din se purane)
  var keys = props.getKeys(), cut = Utilities.formatDate(new Date(now.getTime() - 7 * 864e5), 'Asia/Kolkata', 'yyyy-MM-dd');
  keys.forEach(function (key) { if (key.indexOf('kick_') == 0 && key.slice(5, 15) < cut) props.deleteProperty(key); });
}

// Ek baar Run karo: har 5 min wala timer lagata hai (pehle wala ho to hata ke naya)
function setupTimer() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() == 'kickWorkflows') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('kickWorkflows').timeBased().everyMinutes(5).create();
  console.log('Timer laga: har 5 min kickWorkflows');
}

// Token sahi hai ya nahi, turant jaanch (market band ho tab bhi chalega: live feed khud band ho jaayega)
function testToken() {
  var token = PropertiesService.getScriptProperties().getProperty('GH_TOKEN');
  var res = UrlFetchApp.fetch('https://api.github.com/repos/' + GH_REPO + '/actions/workflows', {
    muteHttpExceptions: true, headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' } });
  console.log('GitHub jawab: ' + res.getResponseCode() + (res.getResponseCode() == 200 ? ' (token theek hai)' : ' ' + res.getContentText().slice(0, 200)));
}
