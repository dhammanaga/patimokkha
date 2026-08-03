const fs=require('fs');
const vm=require('vm');
const ctx={window:{}};
vm.createContext(ctx);
const code=fs.readFileSync('audio/manifest_audio.js','utf8');
vm.runInContext(code, ctx);
const PM=ctx.window.PM_AUDIO;
function show(idx){
  const s=PM.sentences[idx];
  if(!s){console.log('idx',idx,'NOT FOUND');return;}
  console.log('--- idx',idx,'clip=',s.clip,'t0=',s.t0,'t1=',s.t1,'rep=',s.rep);
  (s.words||[]).forEach((w,i)=>console.log('   w'+i, w.p, w.z||'', '['+w.t0+','+w.t1+']'));
}
console.log('=== 第六章 Kathinavaggo paṭhamo 相关句 ===');
[515,516,517,518].forEach(show);

console.log('\n=== src_tail_diag.txt 全表尾部被切统计 ===');
const diag=fs.readFileSync('audio/src_tail_diag.txt','utf8').split('\n');
const cut=diag.filter(l=>/切掉≈/.test(l));
console.log('被切句数量:', cut.length);
const amps=cut.map(l=>parseFloat(l.match(/切掉≈([\d.]+)s/)[1]));
const buckets={'<0.5s':0,'0.5-1s':0,'>=1s':0};
amps.forEach(a=>{const k=a<0.5?'<0.5s':a<1?'0.5-1s':'>=1s';buckets[k]++;});
console.log('分布:', JSON.stringify(buckets));
console.log('最大:', Math.max(...amps).toFixed(2)+'s','最小:', Math.min(...amps).toFixed(2)+'s','均值:', (amps.reduce((a,b)=>a+b,0)/amps.length).toFixed(2)+'s');
console.log('\n样例(前8):');
cut.slice(0,8).forEach(l=>console.log('  '+l.trim()));

console.log('\n=== ctc_tail_probe.txt 全表“真截断-尾词”统计 ===');
const probe=fs.readFileSync('audio/ctc_tail_probe.txt','utf8').split('\n');
const tr=probe.filter(l=>/真截断-尾词/.test(l));
console.log('真截断-尾词句数量:', tr.length);
tr.slice(0,10).forEach(l=>console.log('  '+l.trim()));
