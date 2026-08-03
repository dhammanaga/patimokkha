const fs=require("fs"),vm=require("vm");
const d={window:{}};vm.createContext(d);vm.runInContext(fs.readFileSync("data.js","utf8"),d);
const data=d.window.PATIMOKKHA_DATA;
const s={window:{}};vm.createContext(s);vm.runInContext(fs.readFileSync("audio/manifest_audio.js","utf8"),s);
const sent=s.window.PM_AUDIO.sentences;
function norm(w){ return (w||"").replace(/[()\-.]/g,"").replace(/'/g,"").toLowerCase(); }
[700].forEach(idx=>{
  const dw=data.rules[idx].words.map(w=>w.p);
  const mw=(sent[idx].words||[]).map(w=>w.p);
  const match=dw.length===mw.length && dw.every((w,i)=>norm(w)===norm(mw[i]));
  console.log("idx="+idx+" 词数 data="+dw.length+" mani="+mw.length+" 全词匹配="+match);
  console.log(" data首3:"+JSON.stringify(dw.slice(0,3)));
  console.log(" mani首3:"+JSON.stringify(mw.slice(0,3)));
});
