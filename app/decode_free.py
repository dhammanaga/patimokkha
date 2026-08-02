#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自由 CTC 解码(不给文本目标): 读出某区域录音实际念出的字符+时间,
用于给连读段(无句间静音)建立真实文本时间轴。"""
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
AUDIO_SRC = r"C:\Users\dhamm\Documents\dhammanaga\巴帝摩卡诵\巴帝摩卡诵.善吉祥长老\序20220805_091549.mp3"
CHUNK = 400000
R0 = float(sys.argv[1]) if len(sys.argv) > 1 else 142.0
R1 = float(sys.argv[2]) if len(sys.argv) > 2 else 153.0


def emissions_raw(x_chunk, sess):
    x_chunk = x_chunk.astype(np.float32).reshape(1, len(x_chunk))
    mask = np.ones((1, len(x_chunk)), dtype=np.int64)
    out = sess.run(None, {"input_values": x_chunk, "attention_mask": mask})[0]
    return out[0]


def main():
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    rev = {v: k for k, v in vocab.items()}
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    x, sr = FA.decode_real(AUDIO_SRC, FFMPEG, APP, os.path.join(APP, "audio", "ch2_complete.wav"))
    f0 = int(R0 * FA.SR); f1 = int(R1 * FA.SR)
    xw = x[f0:f1].copy()
    xw = xw - xw.mean(); sd = xw.std()
    if sd > 1e-5:
        xw = xw / sd
    ems = []
    for s in range(0, len(xw), CHUNK):
        e = min(len(xw), s + CHUNK)
        ems.append(emissions_raw(xw[s:e], sess))
    em = np.concatenate(ems, axis=0)
    mx = em.max(axis=1, keepdims=True); z = em - mx; np.exp(z, out=z)
    z = z / z.sum(axis=1, keepdims=True)
    idx = z.argmax(axis=1)
    FRAME = FA.STRIDE / FA.SR
    # greedy 去 blank/重复
    out = []
    prev = -1; start_f = 0
    for t in range(len(idx)):
        c = int(idx[t])
        if c <= 2:  # blank/pad/eos
            if prev >= 4:
                out.append((start_f * FRAME + R0, t * FRAME + R0, rev[prev]))
                prev = -1
            continue
        if c == prev:
            continue
        if prev >= 4:
            out.append((start_f * FRAME + R0, t * FRAME + R0, rev[prev]))
        prev = c; start_f = t
    if prev >= 4:
        out.append((start_f * FRAME + R0, len(idx) * FRAME + R0, rev[prev]))
    print("== 原始字符时间轴 (%.2f-%.2f) ==" % (R0, R1))
    for (a, b, ch) in out:
        print("  %6.2f - %6.2f : %s" % (a, b, ch))
    # 按 >0.30s 空隙聚合为词
    print("\n== 聚合为词 (空隙>0.30s 分词) ==")
    word_chars = []; last_end = None
    for (a, b, ch) in out:
        if last_end is not None and a - last_end > 0.30 and word_chars:
            print("  %6.2f - %6.2f : %s" % (word_chars[0][0], word_chars[-1][1],
                                            "".join(c for _, _, c in word_chars)))
            word_chars = []
        word_chars.append((a, b, ch)); last_end = b
    if word_chars:
        print("  %6.2f - %6.2f : %s" % (word_chars[0][0], word_chars[-1][1],
                                        "".join(c for _, _, c in word_chars)))


if __name__ == "__main__":
    main()
