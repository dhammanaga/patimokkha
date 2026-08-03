// 核查当前 manifest ch7-9: clip 指向 + words 首词 vs data 首词
const fs = require('fs');
const vm = require('vm');
const dataSrc = fs.readFileSync('data.js', 'utf8');
const dSd = { window: {} };
vm.createContext(dSd); vm.runInContext(dataSrc, dSd);
const data = dSd.window.PATIMOKKHA_DATA;
const src = fs.readFileSync('audio/manifest_audio.js', 'utf8');
const sd = { window: {} };
vm.createContext(sd); vm.runInContext(src, sd);
const sent = sd.window.PM_AUDIO.sentences;
function norm(w){ return w.replace(/[()\-]/g,'').replace(/'/g,'').split(' ')[0].toLowerCase(); }
[612,620,630,700,800,900,977,1000,1032,1050,1100,1146].forEach(idx=>{
  const s = sent[idx];
  if(!s){ console.log(`idx=${idx} 无clip记录`); return; }
  const dw0 = data.rules[idx].words[0].p;
  const mw0 = s.words && s.words[0] ? s.words[0].p : '(无words)';
  console.log(`idx=${idx} clip=${s.clip} | manifest首词="${mw0}" data首词="${dw0}" | 匹配=${norm(mw0)===norm(dw0)}`);
});
