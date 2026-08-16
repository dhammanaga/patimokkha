# -*- coding: utf-8 -*-
"""生成校对版 HTML 对照表：所有音频 base64 内嵌（零网络依赖，任何环境可播）"""
import base64, json, os, re, subprocess

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
ROOT = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵"
NODE = r"C:/Users/dhamm/.workbuddy/binaries/node/versions/22.22.2/node.exe"
B64CACHE = {}

def load_js(path, var):
    src = open(path, encoding="utf-8").read()
    return json.loads(re.search(re.escape(var) + r"\s*=\s*(\{.*?\});?\s*$", src, re.S).group(1))

OLD = load_js(os.path.join(APP, "audio", "manifest_audio.js.bak_2202"), "window.PM_AUDIO")["sentences"]
NEW = load_js(os.path.join(APP, "audio", "manifest_audio.js"), "window.PM_AUDIO")["sentences"]
DATA = load_js(os.path.join(APP, "data.js"), "window.PATIMOKKHA_DATA")

# 逐词 TTS 清单（node 转 JSON）
TMP = r"C:/Users/dhamm/AppData/Local/Temp/PW.json"
subprocess.run([NODE, os.path.join(APP, "_extract_words.js"),
                os.path.join(APP, "audio", "words", "manifest_pali_words.js"), TMP], check=True)
WORDS = json.load(open(TMP, encoding="utf-8"))

OVERRIDE = {(34, 10): (15.6, 17.3), (34, 11): (17.3, 19.6)}
TTS_HASH = {}

def w_hash(p):
    k = p.replace("(", "").replace(")", "").strip()
    if k not in WORDS:
        return None
    return WORDS[k].replace("words/", "")

rows = []
for k in range(50):
    o, n = OLD.get(str(k)), NEW.get(str(k))
    if not o or not n:
        continue
    r = DATA["rules"][k]
    for wi, w in enumerate(r.get("words") or []):
        ow = o["words"][wi] if wi < len(o["words"]) else None
        nw = n["words"][wi] if wi < len(n["words"]) else None
        if not ow or not nw or ow.get("t0") is None or nw.get("t0") is None:
            continue
        n0, n1 = nw["t0"], nw["t1"]
        if (k, wi) in OVERRIDE:
            n0, n1 = OVERRIDE[(k, wi)]
        if abs(n0 - ow["t0"]) > 0.35 or abs(n1 - ow["t1"]) > 0.35:
            rows.append((k, wi, w["p"], ow["t0"], ow["t1"], n0, n1))

def safe(n):
    return re.sub(r"[^A-Za-z0-9\u00c0-\u024f_-]", "", n)[:40]

def b64(path):
    """读文件转 base64 data URI（带缓存）"""
    if path in B64CACHE:
        return B64CACHE[path]
    if not os.path.exists(path):
        B64CACHE[path] = None
        return None
    d = open(path, "rb").read()
    if len(d) < 500:
        B64CACHE[path] = None
        return None
    uri = "data:audio/mpeg;base64," + base64.b64encode(d).decode()
    B64CACHE[path] = uri
    return uri

def aud(k, wi, p, tag):
    # TTS 合成句（_tts:true）→ old/new 都用预生成 mp3（男声统一）
    if NEW.get(str(k), {}).get("_tts"):
        h = w_hash(p)
        uri = b64(os.path.join(APP, "audio", "words", h)) if h else None
        if not uri:
            return '<span style="color:#c0392b">缺音频</span>'
        return '<audio controls preload="none" style="height:32px"><source src="%s"></audio>' % uri
    fn = "%03d_%02d_%s_%s.mp3" % (k, wi, safe(p), tag)
    uri = b64(os.path.join(ROOT, "切音对照_audio", fn))
    if not uri:
        return '<span style="color:#c0392b">缺音频</span>'
    return '<audio controls preload="none" style="height:32px"><source src="%s"></audio>' % uri

def sec_label(idx):
    for sec in DATA["sections"]:
        if sec["ruleStart"] <= idx <= sec["ruleEnd"]:
            return "%s · 第%d句（全局#%d）" % (sec["title"], idx + 1, idx + 1)
    return "第%d句" % (idx + 1)

def sent_detail(k):
    """完整句子详情 HTML：原文 + 全句播放 + 逐词译 + 逐词发音（全部内嵌音频）"""
    r = DATA["rules"][k]
    clip = NEW.get(str(k), {}).get("clip", "")
    clip_uri = b64(os.path.join(APP, clip)) if clip else None
    html = '<div style="background:#FBF7EC;border:1px solid #E8E0CE;border-radius:8px;padding:12px 14px">'
    html += '<div style="font-size:15px;line-height:1.7;color:#2E332B"><b>原文：</b>%s</div>' % re.sub(r"<", "&lt;", r.get("pali", ""))
    if clip_uri:
        html += '<div style="margin:8px 0"><b>全句发音：</b><audio controls preload="none" style="height:32px;width:240px"><source src="%s"></audio></div>' % clip_uri
    html += '<div style="font-size:13px;color:#5C6B4F;margin:6px 0"><b>逐词译：</b></div>'
    html += '<div style="display:flex;flex-wrap:wrap;gap:6px">'
    for wi, w in enumerate(r.get("words") or []):
        p = w.get("p", ""); z = w.get("z", "")
        h = w_hash(p)
        if h:
            uri = b64(os.path.join(APP, "audio", "words", h))
            play = '<button onclick="new Audio(\'%s\').play()" style="cursor:pointer;border:none;background:#5C6B4F;color:#fff;border-radius:6px;padding:2px 8px;font-size:12px">▶</button>' % uri if uri else '<span style="color:#B9AFA0;font-size:12px">无音</span>'
        else:
            play = '<span style="color:#B9AFA0;font-size:12px">无音</span>'
        html += '<span style="background:#FFF;border:1px solid #E0D8C4;border-radius:6px;padding:4px 8px;font-size:13px">%s %s <span style="color:#8A7055">%s</span></span>' % (play, re.sub(r"<", "&lt;", p), re.sub(r"<", "&lt;", z))
    html += "</div></div>"
    return html

h = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>巴帝摩卡 · 切音校对表</title>
<style>
body{font-family:"Microsoft YaHei",sans-serif;background:#F6F0E2;color:#2E332B;padding:24px;max-width:1280px;margin:auto}
h1{color:#7A1F2B;font-size:22px}
table{border-collapse:collapse;width:100%;background:#FFFDF7;box-shadow:0 2px 10px rgba(0,0,0,.08);border-radius:10px;overflow:hidden}
th,td{border-bottom:1px solid #E8E0CE;padding:8px 10px;text-align:left;font-size:14px;vertical-align:top}
th{background:#5C6B4F;color:#fff;font-weight:600;position:sticky;top:0}
tr:hover{background:#F4EFE0}
audio{width:150px}
.old{color:#C0392B;font-weight:600}
.new{color:#1E8449;font-weight:600}
.tag{font-size:12px;color:#8A7055;margin:4px 0 12px}
.bar{position:sticky;bottom:0;background:#FFFDF7;border:1px solid #E8E0CE;border-radius:10px;padding:14px 18px;margin-top:14px;display:flex;align-items:center;gap:16px;box-shadow:0 -2px 10px rgba(0,0,0,.06)}
#btn{margin:0 0 0 auto;background:#7A1F2B;color:#fff;border:none;border-radius:8px;padding:10px 26px;font-size:16px;cursor:pointer}
#btn:disabled{background:#B9AFA0;cursor:wait}
#msg{font-size:14px;color:#5C6B4F}
input[type=checkbox]{width:18px;height:18px;accent-color:#1E8449;cursor:pointer}
.viewbtn{cursor:pointer;border:1px solid #C9BFA8;background:#FFF;border-radius:6px;padding:2px 8px;font-size:12px;color:#5C6B4F}
.viewbtn:hover{background:#F0E9D8}
tr.detail td{background:#FBF7EC;border-bottom:1px solid #EFE7D5}
</style></head><body>
<h1>🪷 巴帝摩卡 · 逐词切音校对表</h1>
<p class="tag">1. 点「📖 整句」看原句上下文（原文+全句发音+逐词译+逐词发音）· 2. 听「原发音」与「修改后发音」· 3. 勾选发音正确的词 · 4. 点「提交校对」<br>
提交的勾选项 = 校对通过将更新；<b>未勾选</b> = 还有问题，我会再次调整后重发校对。</p>
<table id="tbl"><tr><th>✓</th><th>句号</th><th>句子标号</th><th>词</th><th>📖</th><th>原切音</th><th>原发音（错）</th><th>修改后切音</th><th>修改后发音（对）</th></tr>
"""
for k, wi, p, o0, o1, n0, n1 in rows:
    h += ('<tr><td><input type="checkbox" class="ck" data-id="%d_%d" checked></td>'
          '<td>%d</td><td class="new">%s</td><td><b>%s</b></td>'
          '<td><button class="viewbtn" data-k="%d" onclick="toggleDet(%d)">📖 整句</button></td>'
          '<td class="old">[%.2f, %.2f]</td><td>%s</td>'
          '<td class="new">[%.2f, %.2f]</td><td>%s</td></tr>'
          '<tr class="detail" id="det_%d" style="display:none"><td colspan="9">%s</td></tr>') % (
        k, wi, k, sec_label(k), p, k, k, o0, o1, aud(k, wi, p, "old"), n0, n1, aud(k, wi, p, "new"), k, sent_detail(k))
h += """</table>
<div class="bar"><span>已勾选 <b id="cnt">%d</b> / %d 个</span>
<div id="msg">（勾选 = 校对通过，将更新到 App）</div>
<button id="btn">提交校对</button></div>
<script>
var cks = document.querySelectorAll('.ck');
function upd(){ var n=0; cks.forEach(function(c){ if(c.checked) n++; }); document.getElementById('cnt').textContent = n; }
cks.forEach(function(c){ c.addEventListener('change', upd); }); upd();
function toggleDet(k){ var d = document.getElementById('det_' + k); d.style.display = (d.style.display === 'none' ? '' : 'none'); }
document.getElementById('btn').addEventListener('click', function(){
  var appr = [];
  cks.forEach(function(c){ if(c.checked) appr.push(c.getAttribute('data-id')); });
  var btn = this; btn.disabled = true; btn.textContent = '提交中…';
  fetch('http://127.0.0.1:8139/submit', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({approved: appr, total: cks.length, ts: Date.now()})})
    .then(function(r){ return r.json(); })
    .then(function(j){
      document.getElementById('msg').textContent = '✅ 已提交 ' + j.approved + ' 个词（校对通过，待更新）。未勾选的 ' + (cks.length - j.approved) + ' 个将再次调整。';
      btn.textContent = '提交成功';
      setTimeout(function(){ btn.disabled = false; btn.textContent = '提交校对'; }, 3000);
    })
    .catch(function(e){ document.getElementById('msg').textContent = '❌ 提交失败（校对服务未启动？）'; btn.disabled = false; btn.textContent = '提交校对'; });
});
</script></body></html>""" % (len(rows), len(rows))
open(os.path.join(ROOT, "切音对照表_0-49.html"), "w", encoding="utf-8").write(h)
print("校对版 HTML（含整句上下文）已生成:", len(rows), "个切错词")
