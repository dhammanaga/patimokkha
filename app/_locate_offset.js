// 精确定位 ch7-9 当前 words 的错位方式：
// 假设重编号 bug = 当前[idx].words 实际是旧[idx+offset].words 平移而来
// 对当前每个 idx 的 words 首词, 在旧 manifest 全表搜索匹配, 记录旧idx, 计算 offset
const fs = require('fs');
const vm = require('vm');
function loadM(f){
  const src = fs.readFileSync(f,'utf8');
  const sd={window:{}}; vm.createContext(sd); vm.runInContext(src,sd);
  return sd.window.PM_AUDIO.sentences;
}
const cur = loadM('audio/manifest_audio.js');
const old = loadM('_manifest_old_ref.js');
function norm(w){ return (w||'').replace(/[()\-.]/g,'').replace(/'/g,'').toLowerCase(); }

// 构建 old 首词索引
const oldFirst = {}; // normfirst -> [oldidx...]
for(const k in old){
  const w = old[k].words; 
  if(w && w[0] && w[0].p){
    const nf = norm(w[0].p.split(' ')[0]);
    (oldFirst[nf]=oldFirst[nf]||[]).push(parseInt(k));
  }
}

// 统计 ch7 cur words 首词对应的 old idx, 看 offset 是否恒定
const offsetCount = {};
for(let idx=612; idx<=976; idx++){
  const cw = cur[idx]; if(!cw||!cw.words||!cw.words[0]) continue;
  const nfc = norm(cw.words[0].p.split(' ')[0]);
  const cand = oldFirst[nfc];
  if(!cand || cand.length===0) continue;
  // 取最近的
  let best = cand[0]; let bd = Math.abs(best-idx);
  for(const o of cand){ const d=Math.abs(o-idx); if(d<bd){bd=d;best=o;} }
  const off = best - idx;
  offsetCount[off]=(offsetCount[off]||0)+1;
}
console.log('ch7 (612-976) 当前words首词 → old idx 的 offset 分布:');
Object.entries(offsetCount).sort((a,b)=>b[1]-a[1]).slice(0,12).forEach(([o,c])=>console.log(`  offset=${o} 出现${c}次`));
