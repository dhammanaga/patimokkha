// 重建全部章节的连续标注音轨为干净、可精确 seek 的 chN_full.m4a，
// 并用 PCM 字节计数法精确测每句时长，写出 chN_map.json（含全部有录音的句子）。
// 同时按 (新总时长/旧总时长) 比例重标定第4章已标边界 ch4_bounds.json。
// 旧 chN_full.mp3（concat -c copy 损坏）在 m4a 成功后删除。
// 用法：node app/rebuild_tracks.js
const { spawn, execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const FFMPEG = "C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe";
const APP = path.resolve(__dirname);
const AUD = path.join(APP, "audio");
const SR = 44100, CH = 1, BPS = 2; // PCM 测时参数

// 解析 data.js 章节
const dataRaw = fs.readFileSync(path.join(APP, "data.js"), "utf8");
const dm = JSON.parse(dataRaw.replace(/^[\s\S]*?window\.PATIMOKKHA_DATA\s*=\s*/, "").replace(/;\s*$/, ""));
const sections = dm.sections;

// 解析备份 manifest 取原始 clip
const bt = fs.readFileSync(path.join(AUD, "manifest_audio.js.bak_realign_1785335099745"), "utf8");
const bman = JSON.parse(bt.replace(/^[\s\S]*?window\.PM_AUDIO\s*=\s*/, "").replace(/;\s*$/, ""));
const bsent = bman.sentences;

// 精确时长：解码成 PCM 并统计字节数（无解析竞态，绝对精确）
function exactDur(f) {
  return new Promise((resolve, reject) => {
    const p = spawn(FFMPEG, ["-i", f, "-vn", "-acodec", "pcm_s16le", "-ar", String(SR), "-ac", String(CH), "-f", "s16le", "-"], { stdio: ["ignore", "pipe", "ignore"] });
    let bytes = 0;
    p.stdout.on("data", c => bytes += c.length);
    p.on("error", e => reject(e));
    p.on("close", () => resolve(bytes / (SR * CH * BPS)));
  });
}

(async () => {
  // 先量旧 ch4_full.mp3 总时长（用于边界重标定）
  const ch4OldMp3 = path.join(AUD, "ch4_full.mp3");
  let ch4OldTotal = null;
  if (fs.existsSync(ch4OldMp3)) ch4OldTotal = await exactDur(ch4OldMp3);

  for (const s of sections) {
    const ch = s.order + 1;
    const start = s.ruleStart, end = s.ruleEnd;
    // 收集本章有录音且文件存在的句子（顺序 = 拼接顺序）
    const idxs = [];
    for (let i = start; i <= end; i++) {
      const e = bsent[String(i)];
      if (e && e.clip && /^audio\/sent/.test(e.clip)) {
        const f = path.join(APP, e.clip);
        if (fs.existsSync(f)) idxs.push(i);
      }
    }
    if (idxs.length === 0) { console.log(`第${ch}章：无录音，跳过。`); continue; }

    const list = [];
    let offset = 0;
    const map = [];
    for (const i of idxs) {
      const f = path.join(APP, bsent[String(i)].clip);
      const d = await exactDur(f);
      list.push("file '" + f.replace(/'/g, "'\\''") + "'");
      map.push({ idx: i, offset: +offset.toFixed(3), dur: +d.toFixed(3) });
      offset += d;
    }
    const m4a = path.join(AUD, "ch" + ch + "_full.m4a");
    const txt = path.join(AUD, "_ch" + ch + "_concat.txt");
    fs.writeFileSync(txt, list.join("\n") + "\n");
    fs.writeFileSync(path.join(AUD, "ch" + ch + "_map.json"), JSON.stringify(map));

    try {
      execFileSync(FFMPEG, ["-y", "-f", "concat", "-safe", "0", "-i", txt, "-c:a", "aac", "-b:a", "96k", "-ar", String(SR), "-ac", String(CH), "-movflags", "+faststart", m4a], { stdio: "ignore", timeout: 600000 });
    } catch (e) {
      console.log(`  ⚠ 第${ch}章重编码失败：${e.message}`);
      continue;
    }
    const sz = (fs.statSync(m4a).size / 1048576).toFixed(2);
    console.log(`第${ch}章：已重建 ch${ch}_full.m4a（${sz}MB, ${map.length}句, 约 ${offset.toFixed(1)}s）`);

    // 旧 mp3 删除（已损坏且可被 m4a 取代）
    const oldMp3 = path.join(AUD, "ch" + ch + "_full.mp3");
    if (fs.existsSync(oldMp3)) { try { fs.unlinkSync(oldMp3); } catch (e) {} }

    // 第4章边界重标定
    if (ch === 4 && ch4OldTotal) {
      const newTotal = map.reduce((a, m) => a + m.dur, 0);
      const factor = newTotal / ch4OldTotal;
      const bpath = path.join(AUD, "ch4_bounds.json");
      if (fs.existsSync(bpath)) {
        const b = JSON.parse(fs.readFileSync(bpath, "utf8"));
        const nb = {};
        for (const k of Object.keys(b)) {
          const v = b[k];
          nb[k] = [+(v[0] * factor).toFixed(3), +(v[1] * factor).toFixed(3)];
        }
        fs.writeFileSync(bpath, JSON.stringify(nb));
        console.log(`  第4章边界已按新/旧总时长比 ${factor.toFixed(5)} 重标定（原总 ${ch4OldTotal.toFixed(1)}s → 新 ${newTotal.toFixed(1)}s）`);
      }
    }
  }
  console.log("全部章节连续音轨已重建为干净 .m4a，map 已用精确时长写出。");
})();
