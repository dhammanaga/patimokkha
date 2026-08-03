/* 把整个巴帝摩卡背诵 app 打包成单一 HTML 文件（资源内联为 base64 data-URI）
 * 用法：node _build_single.js
 * 输出：巴帝摩卡背诵_单文件版.html （约 165MB，含全部真人音 + 助记图 + 文本）
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const APP = 'C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app';
const rp = (p) => path.join(APP, p);
const read = (p) => fs.readFileSync(rp(p), 'utf8');

// 把单个磁盘资源读成 data-URI
function toDataUri(absPath, mime) {
  const b = fs.readFileSync(absPath);
  return 'data:' + mime + ';base64,' + b.toString('base64');
}

// 把 manifest 里的相对路径解析为磁盘真实位置
//   图片：images/pm_X.jpg        -> app/images/pm_X.jpg
//   整句：audio/sent_new/IDX.mp3 -> app/audio/sent_new/IDX.mp3
//   逐词：words/X.mp3            -> app/audio/words/X.mp3  （app 里经 audioBase='audio/' 拼接）
function resolveAsset(x) {
  if (/^words\//.test(x)) return path.join(APP, 'audio', x);
  return rp(x);
}

// 递归遍历对象，把资源相对路径字符串替换为 data-URI（仅替换真实存在的文件）
function subPaths(o) {
  function walk(x) {
    if (typeof x === 'string') {
      if (/^(audio\/|images\/|words\/)/.test(x) || /\.(mp3|jpe?g|png)$/i.test(x)) {
        const fp = resolveAsset(x);
        if (fs.existsSync(fp)) {
          const mime = /\.mp3$/i.test(x) ? 'audio/mpeg' : 'image/jpeg';
          return toDataUri(fp, mime);
        }
      }
      return x;
    }
    if (Array.isArray(x)) return x.map(walk);
    if (x && typeof x === 'object') {
      const r = {};
      for (const k in x) r[k] = walk(x[k]);
      return r;
    }
    return x;
  }
  return walk(o);
}

// 读取一个 manifest 文件（window.X = {...}），返回替换后的 JS 赋值语句
function loadManifest(file, varName) {
  const code = read(file);
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  const obj = sandbox.window[varName];
  if (!obj) throw new Error('var not found: ' + varName + ' in ' + file);
  const sub = subPaths(obj);
  return 'window.' + varName + ' = ' + JSON.stringify(sub) + ';';
}

// 内联脚本安全化：防止内容里的 </script> 提前闭合
const safe = (s) => s.replace(/<\/script>/gi, '<\\/script>');

// —— 1. 样式 ——
const styles = read('styles.css');

// —— 2. 取出 index.html 的 body 标记（去掉外链 script / link）——
const idxHtml = read('index.html');
const bodyInner = idxHtml.split('<body>')[1].split('</body>')[0];
const bodyMarkup = bodyInner.replace(/<script src="[^"]*"><\/script>\s*/g, '').trim();

// —— 3. 各脚本 ——
const parser = safe(read('parser.js'));
const data = safe(read('data.js'));
const wordsManifest = loadManifest('audio/words/manifest_pali_words.js', 'PM_PALI_WORDS');

let paliTts = safe(read('pali-tts.js'));
// 补丁：data: URI 当作绝对路径直接返回，不要被加 audio/ 前缀
paliTts = paliTts
  .replace('test(rel)) return rel;', 'test(rel) || /^data:/i.test(rel)) return rel;')
  .replace('test(wrel)) ? wrel :', 'test(wrel) || /^data:/i.test(wrel)) ? wrel :');

const imagesManifest = loadManifest('images/manifest.js', 'PM_IMAGES');
const audioManifest = loadManifest('audio/manifest_audio.js', 'PM_AUDIO');
const appJs = safe(read('app.js'));

const out = `<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>巴帝摩卡 · 背诵（单文件版）</title>
<style>
${styles}
</style>
</head>
<body>
${bodyMarkup}
<script>${parser}</script>
<script>${data}</script>
<script>${wordsManifest}</script>
<script>${paliTts}</script>
<script>${imagesManifest}</script>
<script>${audioManifest}</script>
<script>${appJs}</script>
</body>
</html>
`;

const outPath = rp('巴帝摩卡背诵_单文件版.html');
fs.writeFileSync(outPath, out, 'utf8');
console.log('WROTE', outPath);
console.log('SIZE', (out.length / 1048576).toFixed(1), 'MB');
