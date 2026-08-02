// 手动标注本地服务器：静态托管 app/ + 接收 /save 写回 manifest_audio.js
// 用法：node app/annotate_server.js  然后浏览器打开 http://localhost:8731/
const http = require("http");
const fs = require("fs");
const path = require("path");

const APP = path.resolve(__dirname);
const PORT = 8731;
const MANIFEST = path.join(APP, "audio", "manifest_audio.js");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".mp3": "audio/mpeg",
  ".m4a": "audio/mp4",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
};

function sendFile(req, res, file) {
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("404 " + file);
      return;
    }
    const ext = path.extname(file).toLowerCase();
    const type = MIME[ext] || "application/octet-stream";
    const total = st.size;
    const range = req.headers.range;
    if (range && /^bytes=/.test(range)) {
      const m = /bytes=(\d*)-(\d*)/.exec(range);
      let start = m[1] ? parseInt(m[1], 10) : 0;
      let end = m[2] ? parseInt(m[2], 10) : total - 1;
      if (isNaN(start) || isNaN(end) || start > end || end >= total) {
        res.writeHead(416, { "Content-Type": "text/plain; charset=utf-8", "Content-Range": "bytes */" + total });
        res.end("416 Range Not Satisfiable");
        return;
      }
      const chunk = end - start + 1;
      res.writeHead(206, {
        "Content-Type": type,
        "Content-Range": "bytes " + start + "-" + end + "/" + total,
        "Accept-Ranges": "bytes",
        "Content-Length": chunk,
        "Cache-Control": "no-cache",
      });
      const stream = fs.createReadStream(file, { start, end });
      stream.on("error", () => { try { res.destroy(); } catch (e) {} });
      stream.pipe(res);
    } else {
      res.writeHead(200, {
        "Content-Type": type,
        "Accept-Ranges": "bytes",
        "Content-Length": total,
        "Cache-Control": "no-cache",
      });
      const stream = fs.createReadStream(file);
      stream.on("error", () => { try { res.destroy(); } catch (e) {} });
      stream.pipe(res);
    }
  });
}

const server = http.createServer((req, res) => {
  // 允许跨域（WorkBuddy 预览面板 58974 等其它源也能 fetch 本服务器）
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Range");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  // 保存标注结果
  if (req.method === "POST" && req.url === "/save") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const obj = JSON.parse(body);
        const data = obj.data;
        if (!data || !data.sentences) throw new Error("invalid payload");
        // 备份
        const stamp = new Date().toISOString().replace(/[:.]/g, "-");
        fs.copyFileSync(MANIFEST, MANIFEST + ".bak_annotate_" + stamp);
        const out =
          "// 真人录音清单（window.PM_AUDIO）\nwindow.PM_AUDIO = " +
          JSON.stringify(data, null, 0) +
          ";\n";
        fs.writeFileSync(MANIFEST, out, "utf-8");
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: true, bytes: out.length }));
      } catch (e) {
        res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: false, error: String(e) }));
      }
    });
    return;
  }

  // 保存整章连续音轨的分句边界（不破坏现有 per-sentence 数据，单独存 JSON）
  if (req.method === "POST" && req.url === "/save2") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const obj = JSON.parse(body);
        const segs = obj.segments;
        if (!segs) throw new Error("invalid payload");
        const out = path.join(APP, "audio", "ch4_segments.json");
        fs.writeFileSync(out, JSON.stringify(segs, null, 0), "utf-8");
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: true, count: Object.keys(segs).length }));
      } catch (e) {
        res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: false, error: String(e) }));
      }
    });
    return;
  }

  // 第4章链式重切：保存边界 [{idx:[start,end],...}] 到 ch4_bounds.json（不动现有分句数据）
  if (req.method === "POST" && req.url === "/save3") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const obj = JSON.parse(body);
        const bounds = obj.bounds;
        if (!bounds || typeof bounds !== "object") throw new Error("invalid payload");
        const out = path.join(APP, "audio", "ch4_bounds.json");
        fs.writeFileSync(out, JSON.stringify(bounds, null, 0), "utf-8");
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: true, count: Object.keys(bounds).length }));
      } catch (e) {
        res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: false, error: String(e) }));
      }
    });
    return;
  }

  // 第4章链式重切：增量提交单句边界到 ch4_bounds.json（保留其它句）
  if (req.method === "POST" && req.url === "/save3one") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const obj = JSON.parse(body);
        const idx = obj.idx;
        const seg = obj.seg;
        if (idx === undefined || !Array.isArray(seg) || seg.length !== 2) throw new Error("invalid payload");
        const out = path.join(APP, "audio", "ch4_bounds.json");
        let cur = {};
        if (fs.existsSync(out)) cur = JSON.parse(fs.readFileSync(out, "utf-8"));
        cur[String(idx)] = [ +(+seg[0]).toFixed(3), +(+seg[1]).toFixed(3) ];
        fs.writeFileSync(out, JSON.stringify(cur, null, 0), "utf-8");
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: true, idx: idx, count: Object.keys(cur).length }));
      } catch (e) {
        res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ ok: false, error: String(e) }));
      }
    });
    return;
  }

  // 读取已存的 ch4_bounds.json（续标用），没有则返回 {}
  if (req.method === "GET" && req.url === "/bounds3") {
    const f = path.join(APP, "audio", "ch4_bounds.json");
    if (fs.existsSync(f)) {
      res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
      res.end(fs.readFileSync(f, "utf-8"));
    } else {
      res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
      res.end("{}");
    }
    return;
  }

  // 通用：章节元数据（data.js sections + 各章 map 句数 / 是否有连续音轨）
  if (req.method === "GET" && req.url.split("?")[0] === "/chapters") {
    try {
      const dataRaw = fs.readFileSync(path.join(APP, "data.js"), "utf8");
      const dm = JSON.parse(dataRaw.replace(/^[\s\S]*?window\.PATIMOKKHA_DATA\s*=\s*/, "").replace(/;\s*$/, ""));
      const out = dm.sections.map((s) => {
        const ch = s.order + 1;
        const mapF = path.join(APP, "audio", "ch" + ch + "_map.json");
        let sentences = 0;
        if (fs.existsSync(mapF)) { try { sentences = JSON.parse(fs.readFileSync(mapF, "utf8")).length; } catch (e) {} }
        const hasAudio = fs.existsSync(path.join(APP, "audio", "ch" + ch + "_full.m4a"));
        return { ch, title: s.title, start: s.ruleStart, end: s.ruleEnd, sentences, hasAudio };
      });
      res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(out));
    } catch (e) {
      res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
      res.end(JSON.stringify({ ok: false, error: String(e) }));
    }
    return;
  }

  // 通用：按章读写边界 chN_bounds.json（?ch=N，默认 4）
  const bm = req.url.split("?")[0].match(/^\/(bounds|saveBounds|saveOne)$/);
  if (bm) {
    const q = new URL(req.url, "http://x").searchParams;
    const ch = q.get("ch") || "4";
    const file = path.join(APP, "audio", "ch" + ch + "_bounds.json");
    if (req.method === "GET") {
      if (fs.existsSync(file)) {
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
        res.end(fs.readFileSync(file, "utf-8"));
      } else {
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
        res.end("{}");
      }
      return;
    }
    if (req.method === "POST") {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        try {
          const obj = JSON.parse(body);
          if (bm[1] === "saveBounds") {
            const bounds = obj.bounds;
            if (!bounds || typeof bounds !== "object") throw new Error("invalid payload");
            fs.writeFileSync(file, JSON.stringify(bounds, null, 0), "utf-8");
            res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
            res.end(JSON.stringify({ ok: true, count: Object.keys(bounds).length, ch }));
          } else if (bm[1] === "saveOne") {
            const idx = obj.idx;
            const seg = obj.seg;
            if (idx === undefined || !Array.isArray(seg) || seg.length !== 2) throw new Error("invalid payload");
            let cur = {};
            if (fs.existsSync(file)) cur = JSON.parse(fs.readFileSync(file, "utf-8"));
            cur[String(idx)] = [ +(+seg[0]).toFixed(3), +(+seg[1]).toFixed(3) ];
            fs.writeFileSync(file, JSON.stringify(cur, null, 0), "utf-8");
            res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
            res.end(JSON.stringify({ ok: true, idx: idx, count: Object.keys(cur).length, ch }));
          }
        } catch (e) {
          res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
          res.end(JSON.stringify({ ok: false, error: String(e) }));
        }
      });
      return;
    }
  }

  // 静态文件
  let urlPath = req.url.split("?")[0];
  if (urlPath === "/") urlPath = "/annotate.html";
  // 防目录穿越
  const safe = path.normalize(urlPath).replace(/^(\.\.[\/\\])+/, "");
  let file = path.join(APP, safe);
  if (!file.startsWith(APP)) {
    res.writeHead(403);
    res.end("forbidden");
    return;
  }
  // 默认首页
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "annotate.html");
  sendFile(req, res, file);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log("标注服务器已启动: http://localhost:" + PORT + "/");
  console.log("manifest 路径: " + MANIFEST);
});
