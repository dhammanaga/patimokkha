#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量自由CTC解码 sent_new/<idx>.mp3, 并报能量 headroom(尾部完整性)。
用法: _dec_clips.py 1144 1145 1161 1162 1163
"""
import sys, os, json
import numpy as np
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:\Users\dhamm\WorkBuddy\巴帝摩卡背诵\app"
SENT = os.path.join(APP, "audio", "sent_new")
CHUNK = 400000
TH = 0.012
WIN = 0.02


def emissions_raw(xc, sess):
    xc = xc.astype(np.float32).reshape(1, len(xc))
    mask = np.ones((1, len(xc)), dtype=np.int64)
    return sess.run(None, {"input_values": xc, "attention_mask": mask})[0][0]


def main():
    ids = [int(a) for a in sys.argv[1:]]
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    tmp = os.path.join(APP, "audio", "_dec_clip_tmp.wav")
    for i in ids:
        p = os.path.join(SENT, "%d.mp3" % i)
        if not os.path.exists(p):
            print("%4d  MISSING" % i); continue
        x, sr = FA.decode_real(p, FFMPEG, APP, tmp)
        D = len(x) / sr
        # headroom: 最后一个能量>TH 的帧到片尾的距离
        step = int(WIN * FA.SR)
        n = max(1, len(x) // step)
        amp = np.array([np.abs(x[k * step:(k + 1) * step]).max() for k in range(n)])
        peak = amp.max() if len(amp) else 1.0
        thr = TH * (peak if peak < 1.0 else 1.0)
        vo = np.where(amp > thr)[0]
        head = (vo[0] * WIN) if len(vo) else 0.0
        tail = D - ((vo[-1] + 1) * WIN) if len(vo) else D
        # 自由解码
        xn = x - x.mean(); sd = xn.std()
        if sd > 1e-5:
            xn = xn / sd
        ems = []
        for s in range(0, len(xn), CHUNK):
            ems.append(emissions_raw(xn[s:min(len(xn), s + CHUNK)], sess))
        em = np.concatenate(ems, axis=0)
        mx = em.max(axis=1, keepdims=True); z = em - mx; np.exp(z, out=z)
        z = z / z.sum(axis=1, keepdims=True)
        idx = z.argmax(axis=1)
        s = "".join(rev[int(c)] for c in idx if int(c) > 2)
        # 折叠重复
        out = []
        prev = None
        for c in idx:
            c = int(c)
            if c <= 2:
                prev = None; continue
            if c == prev:
                continue
            out.append(rev[c]); prev = c
        print("%4d  %5.2fs  前留白%.2f 尾留白%.2f | %s"
              % (i, D, head, tail, "".join(out)))


if __name__ == "__main__":
    main()
