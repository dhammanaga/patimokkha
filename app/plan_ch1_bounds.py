#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 第1章 36 句边界规划 v2 (dry-run):
#  预测落点 = 用全局对齐的"相对句长"预测每句位置, idx0 用真实长(29.19s), 其余用对齐相对长;
#  再把每个预测边界吸附到 ±2.5s 内最近的静音段中点; 最后做单调递增矫正。
import sys, os, json
import numpy as np
import align_ch1_complete as AC
from align_ch1_complete import NAMO, COMPLETE, FFMPEG, APP, AUDIO, CACHE

data = AC.FA.load_js(os.path.join(APP, "data.js"))
rules = data["rules"]
SR = AC.FA.SR
STRIDE = AC.FA.STRIDE

x, _ = AC.FA.decode_real(COMPLETE, FFMPEG, APP, CACHE)
N = len(x) // STRIDE
rms = np.array([np.sqrt(np.mean(x[i*STRIDE:(i+1)*STRIDE]**2)) for i in range(N)])
thr = rms.max() * 0.04
silent = []
i = 0
while i < N:
    if rms[i] < thr:
        j = i
        while j < N and rms[j] < thr:
            j += 1
        if (j - i) * 0.02 >= 0.3:
            silent.append((i*0.02, j*0.02))
        i = j
    else:
        i += 1

raw = json.load(open(os.path.join(AUDIO, "ch1_align_raw.json"), encoding="utf-8"))
gb = {int(k): tuple(v) for k, v in raw["bounds"].items()}
raw_dur = {i: gb[i][1] - gb[i][0] for i in range(36)}

# 预测落点
pred = [0.0]
pred.append(29.19)  # idx0 真实长(Namo x3 含第3遍拖腔)
for i in range(1, 35):
    pred.append(pred[-1] + raw_dur[i])
pred.append(N * 0.02)

# 末尾真实语音结束时刻(录音尾部常有长静音/拖音, 不能取文件末)
last_speech = 0.0
for i in range(N):
    if rms[i] > thr:
        last_speech = i * 0.02
print("能量包络最后语音时刻 = %.2fs (文件总长 %.2fs, 尾部静音约 %.2fs)" %
      (last_speech, N * 0.02, N * 0.02 - last_speech))

# 吸附到最近静音
bounds = [0.0]
for p in pred[1:-1]:
    best = p
    bd = 1e9
    for s, e in silent:
        c = (s + e) / 2
        if abs(c - p) <= 2.5 and abs(c - p) < bd:
            bd = abs(c - p)
            best = c
    bounds.append(best)
bounds.append(last_speech)

# 单调递增矫正: 每句至少 1.0s
for i in range(1, 36):
    if bounds[i] <= bounds[i-1] + 1.0:
        lo = bounds[i-1] + 1.0
        cand = [c for s, e in silent for c in [(s+e)/2] if c >= lo]
        bounds[i] = min(cand) if cand else (bounds[i-1] + 1.5)

print("=== 36 句边界规划 v2 ===")
print("%-4s %-10s %-10s %-10s %-8s" % ("idx", "start", "end", "dur", "orig_dur"))
for idx in range(0, 36):
    s, e = bounds[idx], bounds[idx+1]
    d = e - s
    od = raw_dur[idx]
    flag = "  OK" if 1.0 <= d <= 30 else "  <-- 异常"
    print("%-4d %-10.3f %-10.3f %-10.3f %-8.2f%s" % (idx, s, e, d, od, flag))
print("\n单调递增:", all(bounds[i] < bounds[i+1] for i in range(36)))
print("总时长=%.2f  边界数=%d" % (bounds[-1], len(bounds)))
print("全部合理(1~30s):", all(1.0 <= bounds[i+1]-bounds[i] <= 30 for i in range(36)))
print("idx35 = %.2f~%.2f (%.2fs, orig %.2f)" % (bounds[35], bounds[36], bounds[36]-bounds[35], raw_dur[35]))
