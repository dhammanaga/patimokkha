#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用: 对任意源 mp3 的任意时间段做自由 CTC 解码(地面真相) + 能量静音段检测。
用法: dec_src.py <mp3路径> <t0> <t1> [聚合空隙秒=0.30]
输出: ①字符/词级时间轴(源录音绝对秒) ②能量静音段(可直接用作切点)
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
CHUNK = 400000
ENERGY_TH = 0.012      # 与 tail_integrity.py 一致
WIN = 0.02             # 能量窗 20ms


def emissions_raw(xc, sess):
    xc = xc.astype(np.float32).reshape(1, len(xc))
    mask = np.ones((1, len(xc)), dtype=np.int64)
    return sess.run(None, {"input_values": xc, "attention_mask": mask})[0][0]


def main():
    src = sys.argv[1]
    R0 = float(sys.argv[2]); R1 = float(sys.argv[3])
    GAP = float(sys.argv[4]) if len(sys.argv) > 4 else 0.30
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    tmp = os.path.join(APP, "audio", "_dec_src_tmp.wav")
    x, sr = FA.decode_real(src, FFMPEG, APP, tmp)
    D = len(x) / sr
    if R1 <= 0 or R1 > D:
        R1 = D
    f0 = int(R0 * FA.SR); f1 = int(R1 * FA.SR)
    xw = x[f0:f1].copy()
    print("源时长 %.3fs | 分析区间 %.2f-%.2f (%.2fs)" % (D, R0, R1, R1 - R0))

    # ---- 能量静音段 ----
    step = int(WIN * FA.SR)
    n = max(1, len(xw) // step)
    amp = np.array([np.abs(xw[i * step:(i + 1) * step]).max() for i in range(n)])
    peak = amp.max() if len(amp) else 1.0
    voiced = amp > (ENERGY_TH * max(1.0, peak / max(peak, 1e-9)) if peak < 1 else ENERGY_TH * peak / peak)
    voiced = amp > ENERGY_TH * (peak if peak < 1.0 else 1.0)
    sil = []
    i = 0
    while i < n:
        if not voiced[i]:
            j = i
            while j < n and not voiced[j]:
                j += 1
            a = R0 + i * WIN; b = R0 + j * WIN
            if b - a >= 0.12:
                sil.append((a, b))
            i = j
        else:
            i += 1

    # ---- 自由解码 ----
    xn = xw - xw.mean(); sd = xn.std()
    if sd > 1e-5:
        xn = xn / sd
    ems = []
    for s in range(0, len(xn), CHUNK):
        ems.append(emissions_raw(xn[s:min(len(xn), s + CHUNK)], sess))
    em = np.concatenate(ems, axis=0)
    mx = em.max(axis=1, keepdims=True); z = em - mx; np.exp(z, out=z)
    z = z / z.sum(axis=1, keepdims=True)
    idx = z.argmax(axis=1)
    FRAME = FA.STRIDE / FA.SR
    out = []; prev = -1; start_f = 0
    for t in range(len(idx)):
        c = int(idx[t])
        if c <= 2:
            if prev >= 4:
                out.append((start_f * FRAME + R0, t * FRAME + R0, rev[prev])); prev = -1
            continue
        if c == prev:
            continue
        if prev >= 4:
            out.append((start_f * FRAME + R0, t * FRAME + R0, rev[prev]))
        prev = c; start_f = t
    if prev >= 4:
        out.append((start_f * FRAME + R0, len(idx) * FRAME + R0, rev[prev]))

    print("\n== 解码词块 (空隙>%.2fs 断词) ==" % GAP)
    grp = []; last = None
    def flush():
        if grp:
            print("  %7.2f - %7.2f : %s" % (grp[0][0], grp[-1][1],
                                            "".join(c for _, _, c in grp)))
    for (a, b, ch) in out:
        if last is not None and a - last > GAP and grp:
            flush(); grp = []
        grp.append((a, b, ch)); last = b
    flush()

    print("\n== 能量静音段 (>=0.12s, 阈值 %.3f) ==" % ENERGY_TH)
    for (a, b) in sil:
        print("  %7.2f - %7.2f  (宽 %.2fs, 中点 %.2f)" % (a, b, b - a, (a + b) / 2))
    if not sil:
        print("  (无)")


if __name__ == "__main__":
    main()
