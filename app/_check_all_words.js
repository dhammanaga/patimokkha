const fs = require('fs'), vm = require('vm');
function load(file, expose) {
  const s = { window: {} };
  vm.createContext(s);
  vm.runInContext(fs.readFileSync(file, 'utf8'), s);
  return s.window[expose];
}
const DATA = load(__dirname + '/data.js', 'PATIMOKKHA_DATA');
const AUDIO = load(__dirname + '/audio/manifest_audio.js', 'PM_AUDIO');
const WORDS = load(__dirname + '/audio/words/manifest_pali_words.js', 'PM_PALI_WORDS');

const S = AUDIO.sentences || {};
const noReal = [];   // 无有效真人区间（t0/t1 null）
const missing = [];  // fallback key 不在 PM_PALI_WORDS（点击必无声）
let total = 0, okReal = 0, okTts = 0;

for (let i = 0; i < DATA.rules.length; i++) {
  const r = DATA.rules[i];
  const m = S[String(i)] || (r.key && S[String(AUDIO.key2idx ? AUDIO.key2idx[r.key] : -1)]);
  const ws = (m && m.words) || [];
  (r.words || []).forEach((w, wi) => {
    total++;
    const mw = ws[wi];
    const hasReal = mw && typeof mw.t0 === 'number' && typeof mw.t1 === 'number' && mw.t1 > mw.t0;
    const key = (w.p || '').replace(/[()]/g, '').trim();
    const hasMp3 = !!WORDS[key];
    if (hasReal) { okReal++; return; }
    if (hasMp3) { okTts++; return; }
    missing.push({ idx: i, wi, key, p: w.p, z: w.z });
  });
}

console.log(`总词条: ${total} | 真人发音: ${okReal} | TTS替代: ${okTts} | 点击无声(缺清单): ${missing.length}`);
missing.forEach(x => console.log(`  无声 idx=${x.idx} wi=${x.wi} [${x.p}] key="${x.key}" z="${x.z}"`));
fs.writeFileSync(__dirname + '/_missing_words.json', JSON.stringify(missing, null, 1));
console.log('明细已存 _missing_words.json');
