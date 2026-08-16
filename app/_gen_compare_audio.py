# -*- coding: utf-8 -*-
"""为对照表每个词切出「原切音.mp3」与「修改后.mp3」音频，供听音对比"""
import json, os, re, subprocess, sys
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import forced_align as FA

FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
OUT = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/切音对照_audio"
os.makedirs(OUT, exist_ok=True)

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

def cut(clip, t0, t1, out_mp3):
    # t0/t1 处留 0.05s 余量，避免切掉词首辅音；mp3 流拷贝（无 lame 编码器）
    s = max(0, t0 - 0.05); e = t1 + 0.05
    r = subprocess.run([FFMPEG, "-y", "-i", os.path.join(APP, clip),
                        "-ss", "%.3f" % s, "-to", "%.3f" % e,
                        "-c:a", "copy", out_mp3],
                       capture_output=True, text=True)
    if not os.path.exists(out_mp3) or os.path.getsize(out_mp3) < 500:
        print("  切割失败:", out_mp3, r.stderr[-200:])

def safe(name):
    return re.sub(r"[^A-Za-z0-9\u00c0-\u024f_-]", "", name)[:40]

rows_sorted = sorted(rows, key=lambda x: x[0])
md = "# 巴帝摩卡 · 逐词切音对照表（可听音对比）\n\n范围：第 0-49 句。点击音频对比「原切音（错）」与「修改后（对）」。\n\n| 句 | 词 | 原切音 | 原发音▶ | 修改后切音 | 修改后发音▶ |\n|---|---|---|---|---|---|\n"
for k, wi, p, o0, o1, n0, n1 in rows_sorted:
    clip = NEW.get(str(k))["clip"]
    base = "%03d_%02d_%s" % (k, wi, safe(p))
    f_old = base + "_old.mp3"
    f_new = base + "_new.mp3"
    cut(clip, o0, o1, os.path.join(OUT, f_old))
    cut(clip, n0, n1, os.path.join(OUT, f_new))
    so = os.path.getsize(os.path.join(OUT, f_old))
    sn = os.path.getsize(os.path.join(OUT, f_new))
    link_o = '[▶听](' + os.path.join("切音对照_audio", f_old).replace("\\", "/") + ')' if so > 1000 else "(切出失败)"
    link_n = '[▶听](' + os.path.join("切音对照_audio", f_new).replace("\\", "/") + ')' if sn > 1000 else "(切出失败)"
    md += "| %d | %s | [%.2f, %.2f] | %s | [%.2f, %.2f] | %s |\n" % (k, p, o0, o1, link_o, n0, n1, link_n)
    print("  %d %s 原[%.2f,%.2f]→%s 新[%.2f,%.2f]→%s" % (k, p, o0, o1, f_old, n0, n1, f_new))
md += "\n共 %d 个切错词。音频目录：切音对照_audio/\n" % len(rows_sorted)
open(r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/切音对照表_0-49.md", "w", encoding="utf-8").write(md)
print("完成：对照表 + %d 个音频文件已生成" % (len(rows_sorted)*2))
