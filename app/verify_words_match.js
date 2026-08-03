// 只读校验：全表 manifest.words 首词 vs data.words 首词匹配率，按章统计
const fs = require('fs');
const vm = require('vm');

// 载入 data.js —— 注入 window
const dataSrc = fs.readFileSync('data.js', 'utf8');
const dataSandbox = { window: {} };
vm.createContext(dataSandbox);
vm.runInContext(dataSrc, dataSandbox);
const data = dataSandbox.window.PATIMOKKHA_DATA;
const rules = data.rules;
console.log('data keys =', Object.keys(data));
console.log('meta.ruleCount =', data.meta.ruleCount, ', rules.length =', rules.length);

// 载入 manifest_audio.js
const autSrc = fs.readFileSync('audio/manifest_audio.js', 'utf8');
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(autSrc, sandbox);
const PM_AUDIO = sandbox.window.PM_AUDIO;
const sentences = PM_AUDIO.sentences;
const key2idx = PM_AUDIO.key2idx || {};
console.log('PM_AUDIO keys =', Object.keys(PM_AUDIO));
console.log('sentences count =', Object.keys(sentences).length);

// 章节范围: 从 data.sections 动态读取, 不要硬编码(编号一变就失效)
const chapters = data.sections.map(s => [s.order + 1, s.title, s.ruleStart, s.ruleEnd]);

function chapterOf(idx){
  for(const c of chapters){
    if(idx>=c[2] && idx<=c[3]) return c[1];
  }
  return '未知('+idx+')';
}

function norm(w){
  return w.replace(/[()\-]/g, '').replace(/'/g, '').toLowerCase();
}

let clipCount=0, match=0, noClip=0;
const byCh = {};
for(let idx=0; idx<rules.length; idx++){
  const r = rules[idx];
  const ch = chapterOf(idx);
  byCh[ch]=byCh[ch]||{total:0,clip:0,match:0,nomatch:0,noclip:0};
  byCh[ch].total++;
  const s = sentences[idx];
  if(!s || !s.words || s.words.length===0){
    byCh[ch].noclip++; noClip++;
    continue;
  }
  clipCount++; byCh[ch].clip++;
  const mw = s.words[0];
  const dw = r.words && r.words.length>0 ? r.words[0].p : (r.pali?r.pali.split(' ')[0]:'');
  const ok = mw && dw && norm(mw.p) === norm(dw);
  if(ok){ match++; byCh[ch].match++; } else { byCh[ch].nomatch++; }
}
console.log('\n=== words 匹配率（有 clip 句）===');
let totalClip=0, totalMatch=0;
for(const ch in byCh){
  const c=byCh[ch];
  const pct = c.clip? (100*c.match/c.clip).toFixed(1):'-';
  totalClip+=c.clip; totalMatch+=c.match;
  console.log(`  ${ch}: clip句=${c.clip} 匹配=${c.match} 不匹配=${c.nomatch} 无clip=${c.noclip} 匹配率=${pct}%`);
}
console.log(`\n总: 有clip=${clipCount}(${totalClip}) 匹配=${match}(${totalMatch}) 不匹配=${clipCount-match} 无clip=${noClip}`);
console.log('  整体匹配率 =', (100*match/clipCount).toFixed(1)+'%');

// key2idx 检查
console.log('\n=== key2idx 覆盖 ===');
const keyCount = key2idx ? Object.keys(key2idx).length : 0;
let keyMissing=0, keyOk=0;
for(let idx=0; idx<rules.length; idx++){
  const k = rules[idx].key;
  if(k==null||k===undefined) continue;
  if(key2idx[k]==null){ keyMissing++; } else { keyOk++; }
}
console.log(`  key2idx 条数=${keyCount}, data 中 key 有映射=${keyOk}, 缺失=${keyMissing}`);
