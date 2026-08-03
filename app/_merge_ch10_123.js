/* 把第10章(止争法) 第1、2、3 句 (idx 1147/1148/1149) 合并为一句。
 * 合并后 ruleCount -2, 其后全体 idx -2。
 * 同步: data.js(rules/sections/meta) + sent_new mp3 重命名 + images/manifest.js 旧key合并
 * manifest_audio.js 最大 idx=1142 (<1150), 不受影响 —— 脚本会再校验一次。
 * 用法: node _merge_ch10_123.js [--apply]
 */
const fs = require('fs'), vm = require('vm'), path = require('path');
const APP = __dirname;
const APPLY = process.argv.includes('--apply');

function load(f, n) {
  const c = { window: {} }; vm.createContext(c);
  vm.runInContext(fs.readFileSync(path.join(APP, f), 'utf8'), c);
  return c.window[n];
}

const D = load('data.js', 'PATIMOKKHA_DATA');
const MAN = load('audio/manifest_audio.js', 'PM_AUDIO');
const IMG = load('images/manifest.js', 'PM_IMAGES');

const A = 1147, B = 1149;           // 要合并的区间(含)
const N = B - A + 1;                // 3 句
const SHIFT = N - 1;                // 后续 idx 下移 2

// ---- 0. 前置校验 ----
const r0 = D.rules[A], r1 = D.rules[A + 1], r2 = D.rules[A + 2];
if (!r0 || !r1 || !r2) throw new Error('目标 rule 不存在');
if (r0.pali !== 'Ime kho panāyasmanto') throw new Error('1147 文本不符: ' + r0.pali);
if (r1.pali !== 'satta adhikaraṇa-samathā dhammā') throw new Error('1148 文本不符: ' + r1.pali);
if (r2.pali !== 'uddesaṃ āgacchanti') throw new Error('1149 文本不符: ' + r2.pali);
if (!(r0.secOrder === 9 && r1.secOrder === 9 && r2.secOrder === 9)) throw new Error('secOrder 不都是 9');

const manMax = Math.max(...Object.keys(MAN.sentences).map(Number));
const k2Max = Math.max(...Object.values(MAN.key2idx || {}).map(Number));
console.log('前置校验: manifest.sentences 最大 idx =', manMax, ', key2idx 最大 idx =', k2Max);
if (manMax >= A + N || k2Max >= A + N) {
  throw new Error('音频 manifest 含 >=' + (A + N) + ' 的条目, 需要同步平移 —— 本脚本未实现, 中止');
}
console.log('  → 均 <', A + N, ', 音频 manifest 无需平移 ✓');

// ---- 1. 构造合并句 ----
const merged = {
  idx: A,
  secOrder: 9,
  pali: [r0.pali, r1.pali, r2.pali].join(' '),
  words: [].concat(r0.words || [], r1.words || [], r2.words || []),
  meaning: [r0.meaning, r1.meaning, r2.meaning].join('').replace(/。$/, '') + '。',
  note: [r0.note, r1.note, r2.note].filter(Boolean).join(' '),
  key: [r0.key, r1.key, r2.key].join(' '),
};
console.log('\n合并结果:');
console.log('  pali   :', merged.pali);
console.log('  meaning:', merged.meaning);
console.log('  key    :', merged.key);
console.log('  words  :', merged.words.length, '个 →', merged.words.map(w => w.p).join(' / '));

// ---- 2. 重建 rules ----
const rules = [];
for (let i = 0; i < A; i++) rules.push(D.rules[i]);
rules.push(merged);
for (let i = B + 1; i < D.rules.length; i++) {
  const r = Object.assign({}, D.rules[i]);
  r.idx = i - SHIFT;
  rules.push(r);
}
console.log('\nrules:', D.rules.length, '→', rules.length, '(应为', D.rules.length - SHIFT, ')');
// 校验 idx 连续
for (let i = 0; i < rules.length; i++) if (rules[i].idx !== i) throw new Error('idx 不连续 @' + i);

// ---- 3. sections ----
const sections = D.sections.map(s => Object.assign({}, s));
sections.forEach(s => {
  if (s.ruleStart > B) s.ruleStart -= SHIFT;
  if (s.ruleEnd >= B) s.ruleEnd -= SHIFT;
});
sections.forEach((s, k) => {
  if (s.order !== k) throw new Error('section order 错位 @' + k);
  if (rules[s.ruleStart].secOrder !== k || rules[s.ruleEnd].secOrder !== k)
    throw new Error('section ' + k + ' 边界 secOrder 不符');
  if (s.ruleStart > 0 && rules[s.ruleStart - 1].secOrder === k) throw new Error('section ' + k + ' 起点偏大');
  if (s.ruleEnd < rules.length - 1 && rules[s.ruleEnd + 1].secOrder === k) throw new Error('section ' + k + ' 终点偏小');
});
console.log('\nsections 校验通过:');
sections.forEach(s => console.log('  ', s.order, s.title, s.ruleStart + '-' + s.ruleEnd, '(' + (s.ruleEnd - s.ruleStart + 1) + '句)'));

// ---- 4. meta ----
const meta = Object.assign({}, D.meta, { ruleCount: rules.length });

// ---- 5. mp3 重命名计划 ----
const SENT = path.join(APP, 'audio', 'sent_new');
const renames = [];
for (let i = B + 1; i < D.rules.length; i++) {
  const from = path.join(SENT, i + '.mp3');
  if (fs.existsSync(from)) renames.push([i, i - SHIFT]);
}
console.log('\nmp3 重命名:', renames.length, '个 ', renames.length ? (renames[0][0] + '→' + renames[0][1] + ' … ' + renames[renames.length - 1][0] + '→' + renames[renames.length - 1][1]) : '');

// ---- 6. images 旧 key ----
// 注意: 'ime kho panāyasmanto' 等 key 被多章共用(977/1032/612/361/326 …),
// 绝不能删! 只在合并后的新 key 上新增一条指向同一张图。
const oldKeys = [r0.key, r1.key, r2.key];
const hits = oldKeys.filter(k => IMG && IMG[k]);
const stillUsed = {};
oldKeys.forEach(k => { stillUsed[k] = rules.filter(r => r.key === k).length; });
console.log('images 中命中旧 key:', hits.length ? hits.join(' | ') : '(无)');
oldKeys.forEach(k => console.log('   旧key「' + k + '」合并后仍被', stillUsed[k], '句使用 →', stillUsed[k] ? '保留' : '可删(本脚本仍保留)'));

if (!APPLY) { console.log('\n[演练] 未写入。加 --apply 执行。'); process.exit(0); }

// ================= 写入 =================
const ts = '20260803';
fs.copyFileSync(path.join(APP, 'data.js'), path.join(APP, 'data.js.bak_merge' + ts));
const out = '/* Patimokkha data — generated. Do not edit by hand. */\nwindow.PATIMOKKHA_DATA = '
  + JSON.stringify({ meta, sections, rules }) + ';\n';
fs.writeFileSync(path.join(APP, 'data.js'), out, 'utf8');
console.log('\n✓ data.js 已写入 (备份 data.js.bak_merge' + ts + ')');

// mp3 升序重命名(向下平移, 升序安全)
let ok = 0;
for (const [from, to] of renames) {
  const f = path.join(SENT, from + '.mp3'), t = path.join(SENT, to + '.mp3');
  fs.renameSync(f, t); ok++;
}
console.log('✓ mp3 重命名', ok, '个');

// images: 只为新 key 补一条(指向第一个命中的旧图), 不删任何旧 key(多章共用)
if (hits.length && !IMG[merged.key]) {
  IMG[merged.key] = IMG[hits[0]];
  fs.copyFileSync(path.join(APP, 'images/manifest.js'), path.join(APP, 'images/manifest.js.bak_merge' + ts));
  fs.writeFileSync(path.join(APP, 'images/manifest.js'),
    '/* 插图清单 */\nwindow.PM_IMAGES = ' + JSON.stringify(IMG, null, 1) + ';\n', 'utf8');
  console.log('✓ images/manifest.js 已为合并句新增 key →', IMG[merged.key], '(旧 key 全部保留)');
}
console.log('\n完成。');
