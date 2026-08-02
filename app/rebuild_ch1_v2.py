#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 用尊者提供的【完整录音】重做第1章(36句):
#  1) 解码完整录音, 算能量包络, 探测 >=0.3s 静音段;
#  2) 用"相对句长预测 + 吸附最近静音"确定 36 句边界(句末取最后语音时刻);
#     —— 不再依赖对齐末词时间, 避免 Namo x3 拖腔被误判截断。
#  3) 对每句独立做强制对齐(词级), 最后一遍尾音延伸到句末(根治"断在 sammāsa");
#  4) ffmpeg -c copy 切回 36 个分句 mp3(覆盖旧 sent_new, 先备份);
#  5) 写出 ch1_align.json, 并调用 merge_align_to_manifest 合并回主清单。
import sys, os, json, subprocess, shutil, time
import numpy as np
import align_ch1_complete as AC
from align_ch1_complete import NAMO, MODEL, VOCAB, FFMPEG, APP, AUDIO, COMPLETE, CACHE, SENT_NEW

SR = AC.FA.SR
STRIDE = AC.FA.STRIDE

# ---------- 1. 解码 + 能量 + 静音段 ----------
print("解码完整录音...", flush=True)
x, _ = AC.FA.decode_real(COMPLETE, FFMPEG, APP, CACHE)
N = len(x) // STRIDE
rms = np.array([np.sqrt(np.mean(x[i*STRIDE:(i+1)*STRIDE]**2)) for i in range(N)])
thr = rms.max() * 0.04
last_speech = 0.0
for i in range(N):
    if rms[i] > thr:
        last_speech = i * 0.02
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
print("能量阈值=%.4f  最后语音时刻=%.2fs  静音段=%d" % (thr, last_speech, len(silent)), flush=True)

# ---------- 2. 边界 ----------
data = AC.FA.load_js(os.path.join(APP, "data.js"))
rules = data["rules"]
raw = json.load(open(os.path.join(AUDIO, "ch1_align_raw.json"), encoding="utf-8"))
gb = {int(k): tuple(v) for k, v in raw["bounds"].items()}
raw_dur = {i: gb[i][1] - gb[i][0] for i in range(36)}

pred = [0.0, 29.19]  # idx0 真实长(Namo x3 含拖腔)
for i in range(1, 35):
    pred.append(pred[-1] + raw_dur[i])
pred.append(last_speech)

bounds = [0.0]
for s, e in silent:
    if s < 0.5:
        bounds[0] = (s + e) / 2  # 初始静音中点(去头)
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
# 单调递增矫正
for i in range(1, 36):
    if bounds[i] <= bounds[i-1] + 1.0:
        lo = bounds[i-1] + 1.0
        cand = [c for s, e in silent for c in [(s+e)/2] if c >= lo]
        bounds[i] = min(cand) if cand else (bounds[i-1] + 1.5)
print("边界: idx0 %.2f | idx1 %.2f | idx35 %.2f~%.2f" %
      (bounds[1], bounds[2], bounds[35], bounds[36]), flush=True)

# ---------- 3. 模型 + 逐句对齐 ----------
vocab = json.load(open(VOCAB, encoding="utf-8"))
sess = AC.FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])

has = os.path.isdir(SENT_NEW) and any(os.scandir(SENT_NEW))
BAK = os.path.join(AUDIO, "sent_new_bak_v2_%s" % time.strftime("%Y%m%d_%H%M%S"))
if has:
    shutil.copytree(SENT_NEW, BAK)
    print("备份旧 sent_new ->", BAK, flush=True)
os.makedirs(SENT_NEW, exist_ok=True)

ch1 = {}
for idx in range(0, 36):
    orig = rules[idx]["words"]
    repN = 3 if rules[idx].get("pali", "").strip().lower().startswith(NAMO) else 1
    words_i = [dict(w) for w in orig] * repN
    st0 = bounds[idx]
    st1 = bounds[idx+1]
    seg = x[int(st0*SR):int(st1*SR)]
    D = len(seg) / SR
    res = AC.align_full(seg, D, words_i, vocab, sess)
    assert len(res) == len(words_i)
    # 末词尾音: 若离句末 <5s 则延伸到句末(修 Namo 拖腔), 否则只补 1s(避免 idx35 长尾误延)
    lt0, lt1 = res[-1]
    if (D - lt1) > 5.0:
        lt1 = min(D, lt1 + 1.0)
    res[-1] = (lt0, lt1)
    rel = []
    for j, (wt0, wt1) in enumerate(res):
        p = words_i[j].get("p", "")
        rel.append({"p": p, "t0": round(max(0.0, wt0), 3), "t1": round(min(D, wt1), 3)})
    out = os.path.join(SENT_NEW, "%d.mp3" % idx).replace("\\", "/")
    subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                   "-i", COMPLETE, "-c", "copy", out],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    dur = round(st1 - st0, 3)
    ch1[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0, "t1": dur,
                     "rep": repN, "words": rel}
    print("  idx %2d -> sent_new/%d.mp3 (%.2fs, %d 词, rep=%d)" %
          (idx, idx, dur, len(rel), repN), flush=True)

json.dump(ch1, open(os.path.join(AUDIO, "ch1_align.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("ch1_align.json 写出 (%d 句)" % len(ch1), flush=True)

# ---------- 4. 合并回主清单 ----------
import merge_align_to_manifest as M
print("\n=== 合并回 manifest_audio.js ===", flush=True)
M.main()
