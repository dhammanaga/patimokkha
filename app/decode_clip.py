#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对单个 clip mp3 自由 CTC 解码, 读出实际念出的字符, 判断音频内容。
用法: python dec_clip.py <clip路径> [起始秒] [结束秒]
"""
import sys, os, json, subprocess
import numpy as np
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SR = FA.SR
APP = r"C:\Users\dhamm\WorkBuddy\巴帝摩卡背诵\app"
CHUNK = 400000

def clip_decode(path, r0=None, r1=None):
    x, sr = FA.decode_real(path, FFMPEG, APP, os.path.join(APP, "audio", "_tmp_clip.wav"))
    dur = len(x) / float(sr)
    if r0 is None: r0 = 0.0
    if r1 is None: r1 = dur
    f0 = int(r0*SR); f1 = int(min(r1, dur)*SR)
    xw = x[f0:f1].copy()
    if len(xw) < 1600:
        return dur, "片段过短"
    xw = xw - xw.mean(); sd = xw.std()
    if sd > 1e-5: xw = xw / sd
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    ems = []
    for s in range(0, len(xw), CHUNK):
        e = min(len(xw), s+CHUNK)
        xx = xw[s:e].astype(np.float32).reshape(1, e-s)
        mask = np.ones((1, e-s), dtype=np.int64)
        out = sess.run(None, {"input_values": xx, "attention_mask": mask})[0][0]
        ems.append(out)
    em = np.concatenate(ems, axis=0)
    mx = em.max(axis=1, keepdims=True); z = em-mx; np.exp(z, out=z)
    z = z/z.sum(axis=1, keepdims=True)
    idx = z.argmax(axis=1)
    FRAME = FA.STRIDE/SR
    out=[]; prev=-1; start_f=0
    for t in range(len(idx)):
        c=int(idx[t])
        if c<=2:
            if prev>=4: out.append((start_f*FRAME+r0, t*FRAME+r0, rev[prev])); prev=-1
            continue
        if c==prev: continue
        if prev>=4: out.append((start_f*FRAME+r0, t*FRAME+r0, rev[prev]))
        prev=c; start_f=t
    if prev>=4: out.append((start_f*FRAME+r0, len(idx)*FRAME+r0, rev[prev]))
    # 聚合词
    words_chars=[]
    joined=[]
    if out:
        ws=[(rev_char) for (a,b,rev_char) in out]
    # 聚合为词字符串
    word=[]; last_end=None; merged=[]
    for (a,b,ch) in out:
        if last_end is not None and a-last_end>0.30 and word:
            merged.append("".join(word)); word=[]
        word.append(ch); last_end=b
    if word: merged.append("".join(word))
    return dur, " ".join(merged)

if __name__ == "__main__":
    path = sys.argv[1]
    r0 = float(sys.argv[2]) if len(sys.argv)>2 else None
    r1 = float(sys.argv[3]) if len(sys.argv)>3 else None
    dur, text = clip_decode(path, r0, r1)
    print("clip时长=%.2fs  实读内容:\n%s" % (dur, text))
