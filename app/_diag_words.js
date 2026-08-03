// 诊断 ch7/ch8/ch9 words 不匹配的错位模式：整体偏移 or 局部错位
const fs = require('fs');
const vm = require('vm');

const dataSrc = fs.readFileSync('data.js', 'utf8');
const dataSandbox = { window: {} };
vm.createContext(dataSandbox);
vm.runInContext(dataSrc, dataSandbox);
const data = dataSandbox.window.PATIMOKKHA_DATA;
const rules = data.rules;

const autSrc = fs.readFileSync('audio/manifest_audio.js', 'utf8');
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(autSrc, sandbox);
const sentences = sandbox.window.PM_AUDIO.sentences;

function norm(w){ return w.replace(/[()\-]/g,'').replace(/'/g,'').replace(/\./g,'').toLowerCase(); }

function dumpCh(label, start, end, sampleN){
  console.log(`\n===== ${label} idx ${start}-${end} =====`);
  let offsetZip = {}; // 记录 (idx - wordsIdx) 偏移分布
  let total=0;
  for(let idx=start; idx<=end; idx++){
    const s = sentences[idx];
    if(!s || !s.words || s.words.length===0) continue;
    total++;
    const dw0 = rules[idx].words[0].p;
    const mw0 = s.words[0].p;
    if(norm(mw0)!==norm(dw0)){
      // 尝试在当前 data words 中找 manifest 首词位置
      const target = norm(mw0);
      let found=-1;
      for(let wi=0; wi<rules[idx].words.length; wi++){
        if(norm(rules[idx].words[wi].p)===target){ found=wi; break; }
      }
      const matchText = found>=0 ? `data.words[${found}]` : '不在本句';
      console.log(`  idx=${idx} manifest首词="${mw0}" data首词="${dw0}" ${matchText}`);
    }
  }
  console.log(`  (共 ${total} 有clip句)`);
}

dumpCh('巴吉帝亚(前20)', 612, 631);
dumpCh('应悔过法', 977, 1031);
dumpCh('应学(前15)', 1032, 1046);
