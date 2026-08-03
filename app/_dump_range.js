const fs=require('fs'),vm=require('vm');
function load(f,n){const c={window:{}};vm.createContext(c);vm.runInContext(fs.readFileSync(f,'utf8'),c);return c.window[n];}
const data=load('data.js','PATIMOKKHA_DATA');
const man=load('audio/manifest_audio.js','PM_AUDIO');
const secs=data.sections;
function secOf(i){return secs.find(s=>i>=s.ruleStart&&i<=s.ruleEnd);}
for(let i=1138;i<=1166;i++){
  const r=data.rules[i]; if(!r)continue;
  const s=secOf(i); const no=s? (i-s.ruleStart+1):'?';
  const m=man.sentences[i];
  console.log(`#${i} [${s?s.order:'?'}.${s?s.title:'?'} 第${no}句] clip=${m?'YES':'--'} | ${r.pali}`);
}
