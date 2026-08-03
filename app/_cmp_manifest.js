// 对比：当前 manifest 的 ch7-9 words 首词 是否 = git renumber前(72375a5) 旧 manifest 对应 idx 的 words 首词
const fs = require('fs');
const vm = require('vm');

function loadManifest(file){
  const src = fs.readFileSync(file, 'utf8');
  const sandbox = { window: {} };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return sandbox.window.PM_AUDIO.sentences;
}

// 当前 manifest（可能是 minified 版）
const cur = loadManifest('audio/manifest_audio.js');
// 旧 manifest（git 72375a5，带完整 words）
const old = loadManifest('_manifest_old_ref.js');

function norm(w){ return w.replace(/[()\-]/g,'').replace(/'/g,'').split(' ')[0].toLowerCase(); }

// 找 ch7-9 中"当前 manifest words 首词" vs "旧 manifest 对应 idx words 首词"
let same=0, diff=0, curNoWord=0, oldNoWord=0;
const diffRows=[];
for(let idx=612; idx<=1146; idx++){
  const cw = cur[idx];
  const ow = old[idx];
  const cfirst = cw && cw.words && cw.words[0] ? norm(cw.words[0].p) : null;
  const ofirst = ow && ow.words && ow.words[0] ? norm(ow.words[0].p) : null;
  if(!cfirst){ curNoWord++; }
  if(!ofirst){ oldNoWord++; }
  if(cfirst && ofirst && cfirst===ofirst) same++;
  else {
    diff++;
    if(diffRows.length<15) diffRows.push(`idx=${idx} cur="${cfirst}" vs old="${ofirst}"`);
  }
}
console.log('ch7-9 (612-1146):');
console.log('  当前有words首词=', (612+535-curNoWord), ', 旧有=', (612+535-oldNoWord));
console.log('  首词相同=', same, ', 不同=', diff);
console.log('  (若首词大量相同→当前ch7-9就是renumber bug旧遗留未重建)');
console.log('\n不同样例:'); diffRows.forEach(r=>console.log('  '+r));
