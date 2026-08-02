#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解码源录音某窗口, 输出实际念的文本+时长, 供音文对照诊断。
用法: src_window.py 源mp3 start秒 end秒 [标称文字]"""
import sys, os, json, subprocess
import numpy as np
import tempfile
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA
import re


def norm(s):
    _D = {"ā": "a", "ī": "i", "ū": "u", "ṅ": "n", "ñ": "n", "ṇ": "n", "ṭ": "t",
          "ḍ": "d", "ḷ": "l", "ṃ": "m", "ḥ": "h", "ś": "s", "ṣ": "s", "ṛ": "r", "·": ""}
    s = (s or "").lower()
    for k, v in _D.items():
        s = s.replace(k, v)
    return re.sub(r"[^a-z]", "", s)


def main():
    src, s0, s1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    label = sys.argv[4] if len(sys.argv) > 4 else ""
    MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
    VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    # 解码窗口
    tmp = os.path.join(os.path.dirname(src), "_srcwin.wav")
    r = subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % s0, "-to", "%.3f" % s1,
                        "-i", src, "-ar", "16000", "-ac", "1", "-f", "wav", tmp],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x = np.frombuffer(open(tmp, "rb").read()[44:], dtype=np.int16).astype(np.float32) / 32768.0
    x = x - x.mean(); sd = x.std()
    if sd > 1e-5:
        x = x / sd
    ems = []
    CHUNK = 400000
    for s in range(0, len(x), CHUNK):
        e = min(len(x), s + CHUNK)
        ems.append(sess.run(None, {"input_values": x[s:e].astype(np.float32).reshape(1, -1),
                                   "attention_mask": np.ones((1, e - s), dtype=np.int64)})[0][0])
    em = np.concatenate(ems, axis=0)
    idx = em.argmax(axis=1)
    out = []; prev = -1
    for t in range(len(idx)):
        c = int(idx[t])
        if c <= 2:
            prev = -1; continue
        if c == prev:
            continue
        prev = c; out.append(rev[c])
    dec = norm("".join(out))
    print("窗口 [%.1f-%.1f] 时长%.2fs 标称[%s]" % (s0, s1, s1 - s0, label))
    print("  源录音实际念: %s" % (dec if dec else "(无)"))
    os.remove(tmp)


if __name__ == "__main__":
    main()
