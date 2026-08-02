#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解码单个音频文件, 自由 CTC 输出识别文本(去 blank/重复)。用法: dec_file.py 路径.mp3"""
import sys, os, json
import numpy as np
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
TMP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app/audio/_dec_tmp.wav"

def dec(path):
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    x, sr = FA.decode_real(path, FFMPEG, r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app", TMP)
    x = x - x.mean(); sd = x.std()
    if sd > 1e-5:
        x = x / sd
    ems = []
    for s in range(0, len(x), 400000):
        xc = x[s:s + 400000].astype(np.float32).reshape(1, -1)
        mask = np.ones((1, len(xc[0])), dtype=np.int64)
        ems.append(sess.run(None, {"input_values": xc, "attention_mask": mask})[0][0])
    em = np.concatenate(ems, axis=0)
    mx = em.max(axis=1, keepdims=True); z = em - mx; np.exp(z, out=z)
    z = z / z.sum(axis=1, keepdims=True)
    idx = z.argmax(axis=1)
    out = ''; prev = -1
    for t in range(len(idx)):
        c = int(idx[t])
        if c <= 2:
            prev = -1; continue
        if c == prev:
            continue
        prev = c; out += rev[c]
    return out, len(x) / FA.SR

if __name__ == "__main__":
    for p in sys.argv[1:]:
        txt, dur = dec(p)
        print("%s (%.2fs): %s" % (os.path.basename(p), dur, txt))
