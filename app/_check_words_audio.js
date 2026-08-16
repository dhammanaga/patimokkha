/* 全表校验：data.js 每句 words 数量 vs 真人录音 manifest words 数量 */
var fs = require('fs'), vm = require('vm');
function load(file, expose) {
  var code = fs.readFileSync(file, 'utf8');
  var sandbox = { window: {} };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox.window[expose];
}
var DATA = load(__dirname + '/data.js', 'PATIMOKKHA_DATA');
var AUDIO = load(__dirname + '/audio/manifest_audio.js', 'PM_AUDIO');
var S = AUDIO.sentences || {}, K = AUDIO.key2idx || {};
var total = DATA.rules.length, withRec = 0, noRec = 0, mism = [];
for (var i = 0; i < total; i++) {
  var r = DATA.rules[i];
  var m = S[String(i)] || (r.key && S[String(K[r.key])]);
  if (!m) { noRec++; continue; }
  withRec++;
  var nw = (r.words || []).length, nw2 = (m.words || []).length;
  if (nw !== nw2) mism.push({ idx: i, key: r.key, pali: (r.pali||'').slice(0,30), dataWords: nw, recWords: nw2 });
}
console.log('总句数:', total, '| 有真人录音:', withRec, '| 无录音(逐词将TTS):', noRec);
console.log('词数不一致句数:', mism.length);
mism.slice(0, 40).forEach(function (m) { console.log('  不一致 idx=' + m.idx + ' [' + m.key + '] data=' + m.dataWords + ' rec=' + m.recWords + ' | ' + m.pali); });
