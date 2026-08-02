// 为每一章拼连续音轨 chN_full.mp3，并生成 chN_map.json（每句在音轨中的精确偏移/时长）。
// 用法：node app/build_full_tracks.js
const { execFileSync } = require('child_process');
const fs = require('fs');

const FFMPEG = "C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe";
const APP = "C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app";
const AUD = APP + "/audio";

// 1) 章节范围（来自 data.js）
const dataRaw = fs.readFileSync(APP + "/data.js", "utf8");
const dm = JSON.parse(dataRaw.replace(/^[\s\S]*?window\.PATIMOKKHA_DATA\s*=\s*/, '').replace(/;\s*$/, ''));
const sections = dm.sections; // [{title,order,ruleStart,ruleEnd}]

// 2) 原始 manifest 备份：每句 clip（绝对可靠的原始录音文件名）
const bt = fs.readFileSync(AUD + "/manifest_audio.js.bak_realign_1785335099745", "utf8");
const bman = JSON.parse(bt.replace(/^[\s\S]*?window\.PM_AUDIO\s*=\s*/, '').replace(/;\s*$/, ''));
const bsent = bman.sentences;

// 3) 用 ffmpeg -i 读真实时长（manifest 句级 t0/t1 是旧自动对齐脏数据，不可用）
function clipDur(f) {
  try {
    execFileSync(FFMPEG, ['-i', f], { stdio: ['ignore', 'ignore', 'pipe'] });
  } catch (e) {
    const s = (e.stderr ? e.stderr.toString() : '') + (e.stdout ? e.stdout.toString() : '');
    const m = s.match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/);
    if (m) return (+m[1]) * 3600 + (+m[2]) * 60 + parseFloat(m[3]);
  }
  return null;
}

console.log('开始为各章拼连续音轨…');
let totalBuilt = 0;

for (const s of sections) {
  const ch = s.order + 1;                 // 章号 1..11
  const start = s.ruleStart, end = s.ruleEnd;
  // 收集本章有真人录音的句子
  const idxs = [];
  for (let i = start; i <= end; i++) {
    const e = bsent[String(i)];
    if (e && e.clip && /^audio\/sent/.test(e.clip)) idxs.push(i);
  }
  if (idxs.length === 0) {
    console.log(`第${ch}章「${s.title}」：无真人录音，跳过。`);
    continue;
  }

  // 生成 concat 清单 + 映射表
  const list = [];
  const map = [];
  let offset = 0;
  let missing = 0;
  for (const i of idxs) {
    const clipRel = bsent[String(i)].clip;          // "audio/sent/175.mp3"
    const f = APP + "/" + clipRel;                   // APP/audio/sent/175.mp3
    if (!fs.existsSync(f)) { console.log(`  ⚠ 缺文件 idx ${i}: ${clipRel}`); missing++; continue; }
    const dur = clipDur(f);
    if (dur == null) { console.log(`  ⚠ 读不到时长 idx ${i}: ${clipRel}`); missing++; continue; }
    list.push("file '" + f.replace(/'/g, "'\\''") + "'");
    map.push({ idx: i, offset: +offset.toFixed(3), dur: +dur.toFixed(3) });
    offset += dur;
  }
  if (map.length === 0) { console.log(`第${ch}章：全部缺文件，跳过。`); continue; }

  const out = AUD + "/ch" + ch + "_full.mp3";
  const txt = AUD + "/_ch" + ch + "_concat.txt";
  fs.writeFileSync(txt, list.join("\n") + "\n");
  fs.writeFileSync(AUD + "/ch" + ch + "_map.json", JSON.stringify(map));

  // ch4 已有连续音轨则保留不重建（避免破坏已存 136-146 边界坐标）
  if (ch === 4 && fs.existsSync(out)) {
    console.log(`第${ch}章「${s.title}」：ch4_full.mp3 已存在，仅写出 map（${map.length} 句，约 ${offset.toFixed(1)}s）。`);
  } else {
    execFileSync(FFMPEG, ['-y', '-f', 'concat', '-safe', '0', '-i', txt, '-c', 'copy', out],
      { stdio: 'ignore', timeout: 600000 });
    const sz = (fs.statSync(out).size / 1048576).toFixed(1);
    console.log(`第${ch}章「${s.title}」：已拼 ${map.length} 句 -> ch${ch}_full.mp3 (${sz}MB, 约 ${offset.toFixed(1)}s)${missing ? ' [缺' + missing + '句]' : ''}`);
    totalBuilt++;
  }
}
console.log('完成。共新建 ' + totalBuilt + ' 个连续音轨。');
