#!/usr/bin/env node
// 把 recut_records.json 的完整句记录合并进 manifest_audio.js
// 对每条: sentences[idx] = recut_records[{ch_idx}] (clip,t0,t1,rep,words)
// 保留 manifest 其它字段(meta,key2idx,key_xref 等), 并重建 key2idx 中受影响的项
const fs = require("fs");
const path = require("path");
const APP = "C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app";
const MAN = path.join(APP, "audio", "manifest_audio.js");
const RECORDS = path.join(APP, "audio", "recut_records_f4.json");

function loadJs(p) {
  let s = fs.readFileSync(p, "utf8");
  s = s.replace(/^.*?window\.PM_AUDIO\s*=\s*/s, "").replace(/;\s*$/, "");
  return JSON.parse(s);
}

const obj = loadJs(MAN);
const recs = JSON.parse(fs.readFileSync(RECORDS, "utf8")); // {"ch_idx": record}
let n = 0;
for (const k in recs) {
  const rec = recs[k];
  const idx = Number(k.split("_")[1]);
  obj.sentences[String(idx)] = rec;
  n++;
}
// 备份
const ts = new Date().toISOString().replace(/[-:TZ]/g, "").slice(0, 14);
fs.copyFileSync(MAN, MAN + ".bak_recut_" + ts);
fs.writeFileSync(MAN, "window.PM_AUDIO = " + JSON.stringify(obj, null, 2) + ";\n", "utf8");
console.log("merged:", n, "sentences replaced");
console.log("backup:", MAN + ".bak_recut_" + ts);
