# -*- coding: utf-8 -*-
"""增强对照表：每行切错词附「原区间解码内容」+「对齐区间解码内容」"""
import json, os, re, sys
import numpy as np
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import forced_align as FA

FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
SR = FA.SR
MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
CHUNK = 400000

def load_js(path, var):
    src = open(path, encoding="utf-8").read()
    return json.loads(re.search(re.escape(var) + r"\s*=\s*(\{.*?\});?\s*$", src, re.S).group(1))

OLD = load_js(os.path.join(APP, "audio", "manifest_audio.js.bak_2202"), "window.PM_AUDIO")["sentences"]
NEW = load_js(os.path.join(APP, "audio", "manifest_audio.js"), "window.PM_AUDIO")["sentences"]
DATA = load_js(os.path.join(APP, "data.js"), "window.PATIMOKKHA_DATA")

rows = []
for k in range(50):
    o, n = OLD.get(str(k)), NEW.get(str(k))
    if not o or not n: continue
    r = DATA["rules"][k]
    for wi, w in enumerate(r.get("words") or []):
        ow = o["words"][wi] if wi < len(o["words"]) else None
        nw = n["words"][wi] if wi < len(n["words"]) else None
        if not ow or not nw or ow.get("t0") is None or nw.get("t0") is None: continue
        d0, d1 = abs(nw["t0"]-ow["t0"]), abs(nw["t1"]-ow["t1"])
        if d0 > 0.35 or d1 > 0.35:
            rows.append((k, wi, w["p"], ow["t0"], ow["t1"], nw["t0"], nw["t1"]))

vocab = json.load(open(VOCAB, encoding="utf-8"))
rev = {v: k for k, v in vocab.items()}
sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])

def decode_seg(k, t0, t1):
    m = NEW.get(str(k))
    x, _ = FA.decode_real(m["clip"], FFMPEG, APP, os.path.join(APP, "audio", "_tmp_ct.wav"))
    f0, f1 = int(t0*SR), min(int(t1*SR), len(x))
    xw = x[f0:f1].copy()
    if len(xw) < 1600: return "(过短)"
    xw = xw - xw.mean(); sd = xw.std()
    if sd > 1e-5: xw = xw / sd
    ems = []
    for s0 in range(0, len(xw), CHUNK):
        e = min(len(xw), s0+CHUNK)
        xx = xw[s0:e].astype(np.float32).reshape(1, e-s0)
        mask = np.ones((1, e-s0), dtype=np.int64)
        out = sess.run(None, {"input_values": xx, "attention_mask": mask})[0][0]
        ems.append(out)
    em = np.concatenate(ems, 0)
    ids = em.argmax(1)
    out, prev = [], None
    for i in ids:
        if i == 0: prev = None; continue
        if i == prev: continue
        prev = i
        out.append(rev.get(int(i), "?"))
    return "".join(out)

print("解码中（每词 2 个区间）...")
enhanced = []
for k, wi, p, o0, o1, n0, n1 in rows:
    t_o = decode_seg(k, o0, o1)
    t_n = decode_seg(k, n0, n1)
    enhanced.append((k, wi, p, o0, o1, n0, n1, t_o, t_n))
    print("  idx=%s %s: 原[%.2f,%.2f]念『%s』 | 对齐[%.2f,%.2f]念『%s』" % (k, p, o0, o1, t_o, n0, n1, t_n))

md = "# 巴帝摩卡 · 逐词切音对照表（附原发音 / 修改后发音）\n\n范围：第 0-49 句。\n\n| 句 | 词 | 原切音 | 原区间实际发音 | 修改后切音 | 修改后实际发音 |\n|---|---|---|---|---|---|\n"
for k, wi, p, o0, o1, n0, n1, t_o, t_n in enhanced:
    md += "| %s | %s | [%.2f, %.2f] | %s | [%.2f, %.2f] | %s |\n" % (k, p, o0, o1, t_o, n0, n1, t_n)
md += "\n共 %d 个切错词。\n" % len(enhanced)
open(r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/切音对照表_0-49.md", "w", encoding="utf-8").write(md)
print("对照表已更新（含原/修改后发音）")
