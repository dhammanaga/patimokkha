// 列出所有无真人 clip 的句子（走 TTS 兜底），标明章节、句号、文本
const fs=require("fs"),vm=require("vm");
function loadJs(f,varPrefix){
  const sd={window:{}};vm.createContext(sd);vm.runInContext(fs.readFileSync(f,"utf8"),sd);
  return sd.window;
}
const d=loadJs("data.js").PATIMOKKHA_DATA;
const au=loadJs("audio/manifest_audio.js").PM_AUDIO;
const rules=d.rules, sections=d.sections, sent=au.sentences;

// 章节查找函数：按 idx 找所属 section
function sectionOf(idx){
  for(const s of sections){
    if(idx>=s.ruleStart && idx<=s.ruleEnd) return s;
  }
  return null;
}

// 章内序号（第几句）：idx - ruleStart + 1
const noClip=[];
for(let idx=0;idx<rules.length;idx++){
  const r=rules[idx];
  if(sent[idx] && sent[idx].clip) continue; // 有录音
  const sec=sectionOf(idx);
  const inSecNo=sec ? (idx-sec.ruleStart+1) : null;
  noClip.push({idx, ch:sec?sec.order+1:null, chTitle:sec?sec.title:null,
               inSecNo, pali:r.pali, meaning:r.meaning, key:r.key});
}

console.log("=== 无真人录音句子共 "+noClip.length+" 句（点喇叭走 TTS 兜底）===\n");
let curCh=null;
for(const n of noClip){
  if(n.ch!==curCh){
    curCh=n.ch;
    console.log("\n# 第"+curCh+"章 · "+n.chTitle);
  }
  console.log("  · 章内第"+n.inSecNo+"句 (全局idx="+n.idx+")");
  console.log("    "+n.pali);
  console.log("    ["+n.meaning+"]");
}
