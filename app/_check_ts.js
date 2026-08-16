/* 时间戳合理性：t0/t1 边界、单调、溢出容差 */
var fs = require('fs'), vm = require('vm');
function load(file, expose) {
  var sandbox = { window: {} };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox);
  return sandbox.window[expose];
}
var AUDIO = load(__dirname + '/audio/manifest_audio.js', 'PM_AUDIO');
var S = AUDIO.sentences || {};
var bad = [], warn = 0;
Object.keys(S).forEach(function (k) {
  var m = S[k];
  var ws = m.words || [];
  for (var i = 0; i < ws.length; i++) {
    var w = ws[i];
    if (typeof w.t0 !== 'number' || typeof w.t1 !== 'number') { bad.push({ k: k, wi: i, why: '缺t0/t1', p: w.p }); continue; }
    if (w.t0 < 0 || w.t1 <= w.t0) { bad.push({ k: k, wi: i, why: 't0<0或t1<=t0', p: w.p, t0: w.t0, t1: w.t1 }); continue; }
    if (i > 0 && w.t0 < ws[i - 1].t1 - 0.35) { bad.push({ k: k, wi: i, why: '与上词重叠>0.35s', p: w.p, t0: w.t0, prevT1: ws[i - 1].t1 }); }
    if (i === 0 && m.t0 && w.t0 < m.t0 - 0.6) { bad.push({ k: k, wi: 0, why: '首词早于整句起点>0.6', p: w.p, t0: w.t0, sentT0: m.t0 }); }
    if (i === ws.length - 1 && m.t1 && w.t1 > m.t1 + 0.8) { bad.push({ k: k, wi: i, why: '末词超整句终点>0.8', p: w.p, t1: w.t1, sentT1: m.t1 }); }
    warn++;
  }
});
console.log('词条总数:', warn, '| 异常:', bad.length);
bad.slice(0, 30).forEach(function (b) { console.log('  ' + JSON.stringify(b)); });
