# -*- coding: utf-8 -*-
"""扫描全表括号词（如 (pavāraṇāya)）的音频区间能量，判断是否真有发音。
输出: 每词区间 RMS(dBFS) 与 有声帧时长；明显无声的标记。
"""
import json, os, subprocess, sys
import numpy as np
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import forced_align as FA

FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
SR = FA.SR

def load_js(path, expose):
    import re, vm
    src = open(path, encoding="utf-8").read()
    m = re.search(r"window\.%s\s*=\s*(.*?);?\s*$" % expose, src, re.S)
    return json.loads(m.group(1))

AUDIO = load_js(os.path.join(APP, "audio", "manifest_audio.js"), "PM_AUDIO")
S = AUDIO["sentences"]
silent = []
total = 0
cache = {}
def wave_for(idx):
    if idx in cache: return cache[idx]
    m = S[str(idx)]
    x, sr = FA.decode_real(m["clip"], FFMPEG, APP, os.path.join(APP, "audio", "_tmp_pw.wav"))
    cache[idx] = x
    return x

for k, m in S.items():
    ws = m.get("words") or []
    for i, w in enumerate(ws):
        p = w.get("p", "")
        if "(" not in p and ")" not in p: continue
        total += 1
        t0, t1 = w.get("t0"), w.get("t1")
        if t0 is None or t1 is None or t1 <= t0:
            silent.append((k, i, p, "无t0/t1", 0, 0)); continue
        try:
            x = wave_for(k)
        except Exception as e:
            silent.append((k, i, p, "解码失败", 0, 0)); continue
        f0, f1 = int(t0*SR), min(int(t1*SR), len(x))
        seg = x[f0:f1]
        if len(seg) == 0: silent.append((k, i, p, "空区间", 0, 0)); continue
        rms = float(np.sqrt((seg**2).mean()))
        peak = float(np.abs(seg).max())
        voiced = float((np.abs(seg) > 0.02).mean()) * (t1 - t0)
        rms_db = 20*np.log10(rms+1e-9)
        if peak < 0.10 or voiced < 0.30:
            silent.append((k, i, p, f"peak={peak:.3f} rms={rms_db:.1f}dB 有声{voiced:.2f}s", t0, t1))
print(f"括号词总数: {total} | 疑似无声: {len(silent)}")
for s in silent:
    print("  idx=%s wi=%d %s %s [%s,%s]" % (s[0], s[1], s[2], s[3], round(s[4],2) if s[4] else '-', round(s[5],2) if s[5] else '-'))
