// 用 ffmpeg 真实解码时长重写所有 chN_map.json（修复容器时长偏短导致的偏移错位）。
// 连续音轨 chN_full.mp3 是整段 concat，无需重建；只修正映射表的 dur/offset。
// 顺序执行（避免并发截断 time= 解析），解码失败用旧时长兜底，并严格保留原表句集合。
// 用法：node app/regen_maps_accurate.js
const { spawn } = require('child_process');
const fs = require('fs');

const FFMPEG = "C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe";
const APP = "C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app";
const AUD = APP + "/audio";

const dataRaw = fs.readFileSync(APP + "/data.js", "utf8");
const dm = JSON.parse(dataRaw.replace(/^[\s\S]*?window\.PATIMOKKHA_DATA\s*=\s*/, '').replace(/;\s*$/, ''));
const sections = dm.sections;

const bt = fs.readFileSync(AUD + "/manifest_audio.js.bak_realign_1785335099745", "utf8");
const bman = JSON.parse(bt.replace(/^[\s\S]*?window\.PM_AUDIO\s*=\s*/, '').replace(/;\s*$/, ''));
const bsent = bman.sentences;

// 真实解码时长：ffmpeg -i clip -f null - 取最后一行 time=HH:MM:SS.xx（顺序调用，避免截断）
function accurateDur(f) {
  return new Promise((resolve, reject) => {
    const p = spawn(FFMPEG, ['-i', f, '-f', 'null', '-'], { stdio: ['ignore', 'ignore', 'pipe'] });
    let buf = '';
    p.stderr.on('data', c => buf += c.toString());
    p.on('error', e => reject(e));
    p.on('close', () => {
      const lines = buf.split('\n');
      let last = null;
      for (const l of lines) {
        const m = l.match(/time=(\d+):(\d+):(\d+(?:\.\d+)?)/);
        if (m) last = (+m[1]) * 3600 + (+m[2]) * 60 + parseFloat(m[3]);
      }
      resolve(last);
    });
  });
}

async function durWithRetry(f) {
  for (let tries = 0; tries < 2; tries++) {
    try {
      const d = await accurateDur(f);
      if (d != null && d > 0) return d;
    } catch (e) { /* retry */ }
  }
  return null;
}

(async () => {
  for (const s of sections) {
    const ch = s.order + 1;
    const mapPath = AUD + "/ch" + ch + "_map.json";
    if (!fs.existsSync(mapPath)) { console.log(`第${ch}章：无 map，跳过`); continue; }
    const old = JSON.parse(fs.readFileSync(mapPath, "utf8"));
    console.log(`第${ch}章：顺序探测 ${old.length} 句真实时长…`);
    const map = [];
    let offset = 0, fail = 0;
    for (const o of old) {
      const clipRel = bsent[String(o.idx)] && bsent[String(o.idx)].clip;
      const f = clipRel ? (APP + "/" + clipRel) : null;
      let d = (f && fs.existsSync(f)) ? await durWithRetry(f) : null;
      if (d == null) { d = o.dur; fail++; console.log(`  ⚠ idx ${o.idx} 用旧时长兜底 ${d}s`); }
      map.push({ idx: o.idx, offset: +offset.toFixed(3), dur: +d.toFixed(3) });
      offset += d;
    }
    fs.writeFileSync(mapPath, JSON.stringify(map));
    console.log(`  第${ch}章 map 已重写（${map.length}句，约 ${offset.toFixed(1)}s）${fail ? ' [兜底' + fail + ']' : ''}`);
  }
  console.log("全部 map 已用真实解码时长重写完成。连续音轨无需重建。");
})();
