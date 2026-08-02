/* serve_app.js — 巴帝摩卡背诵主应用本地静态服务器（支持 HTTP Range，localhost 即安全上下文，可启用麦克风录音）
 * 用法：node app/serve_app.js   然后浏览器开 http://127.0.0.1:8741/
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PORT = 8741;
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.mp3': 'audio/mpeg', '.jpg': 'image/jpeg', '.png': 'image/png', '.svg': 'image/svg+xml',
  '.webm': 'audio/webm'
};

function sendFile(res, file) {
  fs.stat(file, (err, stat) => {
    if (err) { res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end('404 ' + file); return; }
    const total = stat.size;
    const range = res.req && res.req.headers && res.req.headers['range'];
    if (range) {
      const m = /bytes=(\d*)-(\d*)/.exec(range);
      let start = m && m[1] ? parseInt(m[1], 10) : 0;
      let end = m && m[2] ? parseInt(m[2], 10) : total - 1;
      if (isNaN(start) || isNaN(end) || start > end || end >= total) { res.writeHead(416); res.end(); return; }
      res.writeHead(206, {
        'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
        'Content-Range': 'bytes ' + start + '-' + end + '/' + total,
        'Accept-Ranges': 'bytes', 'Content-Length': (end - start + 1)
      });
      fs.createReadStream(file, { start, end }).pipe(res);
    } else {
      res.writeHead(200, {
        'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
        'Accept-Ranges': 'bytes', 'Content-Length': total
      });
      fs.createReadStream(file).pipe(res);
    }
  });
}

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Range');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  const file = path.join(ROOT, path.normalize(p).replace(/^(\.\.[\/\\])+/, ''));
  if (!file.startsWith(ROOT)) { res.writeHead(403); res.end('forbidden'); return; }
  sendFile(res, file);
});
server.listen(PORT, '127.0.0.1', () => console.log('巴帝摩卡背诵主应用已启动： http://127.0.0.1:' + PORT + '/'));
