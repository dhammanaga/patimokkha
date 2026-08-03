/* 重切 358/359/360 后, 同步更新 manifest_audio.js 的 t1 与逐词时间戳
 * 词时间按字符数加权分配（与既有 fix_ch10_tail_ch11.py 同法）
 */
const fs = require('fs'), vm = require('vm'), path = require('path');
function load(f, n) { const c = { window: {} }; vm.createContext(c); vm.runInContext(fs.readFileSync(f, 'utf8'), c); return c.window[n]; }

const APPLY = process.argv.includes('--apply');
const MAN = load('audio/manifest_audio.js', 'PM_AUDIO');

// 重切后的实测时长 + 首音/末音位置（来自 _dec_clips 的前后留白）
// exact: 由逐音节自由解码得到的真实词边界（源秒 − 该 clip 的 ss 偏移）
const NEW = {
  // ss=124.78, 音节: pari 124.88 / tangdaara 125.28 / janmha 125.80 / tea 126.26 → 末 126.46
  358: { dur: 1.796, lead: 0.02, tail: 0.01 },
  // ss=126.52, 音节: da(tasmā) 126.60 / tu 127.22 / e-wa-m(evametaṃ) 127.70 / daararaa(dhārayāmīti) 128.42 → 末 129.40
  359: {
    dur: 3.072, lead: 0.00, tail: 0.01,
    exact: [[0.08, 0.70], [0.70, 1.18], [1.18, 1.90], [1.90, 2.92]],
  },
  // ss=130.06, 音节: a-ni-y-a(Aniyatuddeso) 130.18 / tea 130.70 ... nitth 131.22 → 末 132.06
  360: { dur: 2.232, lead: 0.00, tail: 0.01, exact: [[0.12, 1.10], [1.10, 2.02]] },
};

let changed = 0;
for (const [k, info] of Object.entries(NEW)) {
  const idx = +k;
  const s = MAN.sentences[idx];
  if (!s) { console.log('✗ manifest 无', idx); continue; }
  const words = s.words || [];
  if (!words.length) { console.log('✗', idx, '无 words'); continue; }

  const t0 = info.lead;
  const t1 = info.dur - info.tail;
  const span = t1 - t0;

  let newWords;
  if (info.exact && info.exact.length === words.length) {
    // 用逐音节解码得到的真实边界
    newWords = words.map((w, i) => ({
      p: w.p, z: w.z || '',
      t0: +info.exact[i][0].toFixed(3), t1: +info.exact[i][1].toFixed(3),
    }));
  } else {
    // 按字符数加权
    const lens = words.map(w => (w.p || '').replace(/[^\p{L}]/gu, '').length || 1);
    const total = lens.reduce((a, b) => a + b, 0);
    let acc = t0;
    newWords = words.map((w, i) => {
      const seg = span * (lens[i] / total);
      const a = acc, b = acc + seg;
      acc = b;
      return { p: w.p, z: w.z || '', t0: +a.toFixed(3), t1: +b.toFixed(3) };
    });
  }

  console.log('--- idx', idx, '---');
  console.log('  t1:', s.t1, '→', +info.dur.toFixed(3));
  newWords.forEach((w, i) => console.log('   ', w.p, ':', words[i].t0 + '-' + words[i].t1, '→', w.t0 + '-' + w.t1));

  if (APPLY) {
    s.t1 = +info.dur.toFixed(3);
    s.words = newWords;
    changed++;
  }
}

if (APPLY) {
  const p = 'audio/manifest_audio.js';
  const ts = '20260803b';
  fs.copyFileSync(p, p + '.bak_' + ts);
  fs.writeFileSync(p, '/* 真人整句录音清单 */\nwindow.PM_AUDIO = ' + JSON.stringify(MAN) + ';\n', 'utf8');
  console.log('\n✓ 已写回 manifest_audio.js，改动', changed, '条；备份', p + '.bak_' + ts);
} else {
  console.log('\n(演练模式，加 --apply 生效)');
}
