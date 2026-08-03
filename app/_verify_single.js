const fs = require('fs');
const s = fs.readFileSync('巴帝摩卡背诵_单文件版.html', 'utf8');
function findAll(re) {
  const r = []; let m;
  re.lastIndex = 0;
  while ((m = re.exec(s))) { r.push(m[0]); if (r.length > 60) break; }
  return r;
}
const a = findAll(/audio\/sent_new\/\d+\.mp3/g);
const im = findAll(/images\/pm_\d+\.jpg/g);
const w = findAll(/words\/[0-9a-f]+\.mp3/g);
console.log('LEFT audio/sent_new :', a.length, a.slice(0, 20));
console.log('LEFT images/pm_      :', im.length, im.slice(0, 20));
console.log('LEFT words/          :', w.length, w.slice(0, 20));
console.log('--- structure ---');
console.log('starts <!DOCTYPE html>:', s.startsWith('<!DOCTYPE html>'));
console.log('ends </html>         :', s.trimEnd().endsWith('</html>'));
console.log('<script> open count  :', (s.match(/<script>/g) || []).length);
console.log('</script> close count:', (s.match(/<\/script>/g) || []).length);
console.log('data:audio embedded  :', (s.match(/data:audio\/mpeg;base64,/g) || []).length);
console.log('data:image embedded  :', (s.match(/data:image\/jpeg;base64,/g) || []).length);
console.log('total size MB        :', (s.length / 1048576).toFixed(1));
