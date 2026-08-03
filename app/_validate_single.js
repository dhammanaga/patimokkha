const fs = require('fs');
const vm = require('vm');
const file = '巴帝摩卡背诵_单文件版.html';
const s = fs.readFileSync(file, 'utf8');

// 1) 抽取 7 个 <script> 块并做语法编译检查（捕获 safe() 转义或拼接破坏）
const re = /<script>([\s\S]*?)<\/script>/g;
let m, blocks = [];
while ((m = re.exec(s))) blocks.push(m[1]);
console.log('script blocks:', blocks.length);
blocks.forEach((b, i) => {
  try { new vm.Script(b, { filename: 'block' + i }); }
  catch (e) { console.log('  !! block', i, 'SYNTAX ERROR:', e.message); process.exitCode = 1; }
});
console.log('syntax compile: all blocks OK');

// 2) 在 window 沙箱里加载 data + 三个 manifest，校验数据完整性
const sandbox = { window: {}, console };
vm.createContext(sandbox);
['data.js', 'words', 'images', 'audio'].forEach(() => {}); // noop
// 找到对应块：顺序是 parser,data,words,tts,images,audio,app
function runBlock(idx, label) {
  try { vm.runInContext(blocks[idx], sandbox, { filename: label }); }
  catch (e) { console.log('  !! run', label, 'ERROR:', e.message); process.exitCode = 1; }
}
runBlock(1, 'data');
runBlock(2, 'wordsManifest');
runBlock(4, 'imagesManifest');
runBlock(5, 'audioManifest');

const w = sandbox.window;
const PMA = w.PM_AUDIO, PALI = w.PM_PALI_WORDS, PIMG = w.PM_IMAGES, PD = w.PATIMOKKHA_DATA;

console.log('--- data integrity ---');
console.log('PATIMOKKHA_DATA sections:', PD && PD.sections ? PD.sections.length : 'MISSING');
console.log('PM_AUDIO.sentences:', PMA && PMA.sentences ? Object.keys(PMA.sentences).length : 'MISSING');
console.log('PM_PALI_WORDS:', PALI ? Object.keys(PALI).length : 'MISSING');
console.log('PM_IMAGES:', PIMG ? Object.keys(PIMG).length : 'MISSING');

function allPrefix(obj, prefix, desc) {
  let bad = 0, total = 0;
  for (const k in obj) {
    const v = (typeof obj[k] === 'object' && obj[k]) ? (obj[k].clip || '') : obj[k];
    if (typeof v === 'string') { total++; if (!v.startsWith(prefix)) bad++; }
  }
  console.log(desc + ': ' + total + ' entries, ' + bad + ' NOT ' + prefix);
  if (bad > 0) process.exitCode = 1;
}
allPrefix(PMA.sentences, 'data:audio', '  sentence clips');
allPrefix(PALI, 'data:audio', '  word audios  ');
allPrefix(PIMG, 'data:image', '  image paths  ');
console.log('DONE exitCode=', process.exitCode || 0);
