#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼接 N+N+1, 用能量静音检测看拼接点 L 附近是否有停顿。
结论: L 附近有静音 -> N 完整收尾(非切); 语音连续穿过 L -> N 末词被切。
"""
import os, re, json, subprocess, sys
import numpy as np

APP = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(APP, "audio", "manifest_audio.js")
FF = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
TMP = os.path.join(APP, "audio", "_tmp_join")
SR = 16000
WIN = 0.010
TH = 0.012

def load_manifest():
    t = open(MANIFEST, encoding="utf-8").read()
    return json.loads(re.search(r"window\.PM_AUDIO\s*=\s*(\{.*\})\s*;?\s*$", t, re.S).group(1))

def pcm(path):
    r = subprocess.run([FF, "-v", "error", "-i", path, "-ar", str(SR), "-ac", "1",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0

def envelope(x):
    n = int(WIN * SR); m = len(x) // n
    if m == 0: return np.array([])
    return np.sqrt((x[:m * n].reshape(m, n) ** 2).mean(1))

def ffjoin(a, b, dst):
    os.makedirs(TMP, exist_ok=True)
    lst = os.path.join(TMP, "_list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("file '%s'\nfile '%s'\n" % (a.replace("\\", "/"), b.replace("\\", "/")))
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                   "-i", lst, "-c", "copy", dst], capture_output=True)

def main():
    a = load_manifest()
    s = a["sentences"]
    pairs = [(939,940),(941,942),(954,955),(957,958),(1089,1090)]
    for idx, idx2 in pairs:
        k, k2 = str(idx), str(idx2)
        pa = os.path.join(APP, s[k]["clip"]); pb = os.path.join(APP, s[k2]["clip"])
        if not (os.path.exists(pa) and os.path.exists(pb)):
            print("%d/%d 文件缺失" % (idx, idx2)); continue
        joined = os.path.join(TMP, "j.mp3")
        ffjoin(pa, pb, joined)
        xj = pcm(joined)
        total = len(xj) / SR
        L = len(pcm(pa)) / SR
        e = envelope(xj)
        sil = []
        i = 0
        while i < len(e):
            if e[i] <= TH:
                j = i
                while j < len(e) and e[j] <= TH: j += 1
                a0 = i * WIN; b0 = j * WIN
                if b0 - a0 >= 0.10:
                    sil.append((a0, b0))
                i = j
            else:
                i += 1
        # 看拼接点附近 ±1.2s 的静音段
        near = [(r0, r1) for (r0, r1) in sil if (r0 - 1.2) <= L <= (r1 + 1.2)]
        print("=== %d|%d  L=%.3fs  total=%.3fs  末词=%s / 下句首词=%s"
              % (idx, idx2, L, total, (s[k].get("words") or [])[-1].get("p"),
                 (s[k2].get("words") or [{}])[0].get("p")))
        print("  拼接点 L 附近(±1.2s)静音段:")
        if near:
            for r0, r1 in near:
                tag = "←含拼接点(完整)" if (r0 <= L <= r1) else ("拼接点前" if r1 <= L else "拼接点后")
                print("    %.3f-%.3f (宽%.2fs) %s" % (r0, r1, r1 - r0, tag))
        else:
            print("    无静音段 → 语音从 %d 连续穿过拼接点进入 %d (疑似被切)" % (idx, idx2))
        # 末词 t1 与 L 关系
        lw = (s[k].get("words") or [])[-1]
        print("  末词%s t1=%.3f  vs L=%.3f  余量=%.3fs" % (lw.get("p"), lw.get("t1"), L, L - lw.get("t1")))
        print()

if __name__ == "__main__":
    main()
