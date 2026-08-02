#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 第1章 重建 v3 —— 用【全局词级对齐】定边界(不再用会漂移的"预测长度+静音吸附")。
#
# 关键修正: 上一版(rebuild_ch1_v2)用全局对齐的"相对句长"预测每句落点, 再吸附到±2.5s内
# 最近静音。该预测因 idx0 第三遍被截断而整体漂移, 在 idx4/5/6 附近吸附失败, 导致 idx5
# 错拿 idx6 的音频、后续整段偏移。
#
# 本版: 对完整录音做全局词级对齐, 每句边界 = 该句【最后一个词结束时刻】之后的第一个真静音
#       (idx0 特殊: 取 26.7s 之后的静音, 覆盖第三遍拖腔)。这样每句锚定在自己的词上, 物理
#       上不可能串句。再逐句独立对齐出词时, 合并回主清单。
import sys, os, json, subprocess, time, shutil
import numpy as np
import align_ch1_complete as AC
from align_ch1_complete import NAMO, MODEL, VOCAB, FFMPEG, APP, AUDIO, COMPLETE, CACHE, SENT_NEW
import merge_align_to_manifest as M

SR = AC.FA.SR
STRIDE = AC.FA.STRIDE
LEAD = 0.10      # 句首前导
TAIL = 0.35      # 句尾拖尾
VERIFY_IDX = [4, 5, 6]   # 之前错配的句, 用于核对


def next_silence_after(silent, t, minlen=0.3):
    for s, e in silent:
        if e >= t and (e - s) >= minlen:
            return (s + e) / 2
    return None


def main():
    # 1) 解码 + 能量/静音段
    print("解码完整录音...", flush=True)
    x, _ = AC.FA.decode_real(COMPLETE, FFMPEG, APP, CACHE)
    D = len(x) / SR
    N = len(x) // STRIDE
    rms = np.array([np.sqrt(np.mean(x[i * STRIDE:(i + 1) * STRIDE] ** 2)) for i in range(N)])
    thr = rms.max() * 0.04
    silent = []
    i = 0
    while i < N:
        if rms[i] < thr:
            j = i
            while j < N and rms[j] < thr:
                j += 1
            if (j - i) * 0.02 >= 0.3:
                silent.append((i * 0.02, j * 0.02))
            i = j
        else:
            i += 1
    print("能量阈值=%.4f  静音段=%d  文件时长=%.2fs" % (thr, len(silent), D), flush=True)

    # 2) 全局词级对齐(分块过模型 + 向量化 Viterbi)
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = AC.FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = AC.FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    all_words = []
    seg_ranges = []
    for idx in range(0, 36):
        orig = rules[idx]["words"]
        repN = 3 if rules[idx].get("pali", "").strip().lower().startswith(NAMO) else 1
        words = [dict(w) for w in orig] * repN
        seg_ranges.append((len(all_words), len(all_words) + len(words)))
        all_words.extend(words)
    t0 = time.time()
    res = AC.align_full(x, D, all_words, vocab, sess)
    print("全局对齐完成: %.1fs  K=%d" % (time.time() - t0, len(res)), flush=True)
    assert len(res) == len(all_words)
    # 每句全局词时范围
    g0, g1 = [], []
    for s, e in seg_ranges:
        wseg = res[s:e]
        g0.append(min(r[0] for r in wseg))
        g1.append(max(r[1] for r in wseg))

    # 3) 用全局词时定边界(每句锚定在自己的词上)
    start = [0.0] * 36
    end = [0.0] * 36
    start[0] = max(0.0, g0[0] - LEAD)
    end0 = next_silence_after(silent, 26.7)   # idx0 第三遍拖腔后的静音
    end[0] = end0 if end0 is not None else min(D, g1[0] + 1.0)
    for i in range(1, 35):
        start[i] = max(end[i - 1], g0[i] - LEAD)
        en = g1[i] + TAIL
        cap = g0[i + 1] - LEAD
        if en > cap:
            en = cap
        end[i] = min(en, D)
    start[35] = max(end[34], g0[35] - LEAD)
    end[35] = min(D, g1[35] + TAIL)
    # 单调兜底
    for i in range(1, 36):
        if start[i] <= end[i - 1] + 0.2:
            start[i] = end[i - 1] + 0.3
        if end[i] <= start[i] + 0.5:
            end[i] = start[i] + 1.0
    end[35] = max(end[35], start[35] + 0.5)

    # 4) 备份旧 sent_new + 逐句切片 + 逐句独立对齐
    has = os.path.isdir(SENT_NEW) and any(os.scandir(SENT_NEW))
    BAK = os.path.join(AUDIO, "sent_new_bak_v3_%s" % time.strftime("%Y%m%d_%H%M%S"))
    if has:
        shutil.copytree(SENT_NEW, BAK)
        print("备份旧 sent_new ->", BAK, flush=True)
    os.makedirs(SENT_NEW, exist_ok=True)

    ch1 = {}
    for idx in range(0, 36):
        orig = rules[idx]["words"]
        repN = 3 if rules[idx].get("pali", "").strip().lower().startswith(NAMO) else 1
        words_i = [dict(w) for w in orig] * repN
        st0, st1 = start[idx], end[idx]
        seg = x[int(st0 * SR):int(st1 * SR)]
        Dseg = len(seg) / SR
        r = AC.align_full(seg, Dseg, words_i, vocab, sess)
        assert len(r) == len(words_i)
        # 末词尾音延伸到句末(修 Namo 拖腔 / 长尾)
        lt0, lt1 = r[-1]
        if (Dseg - lt1) > 5.0:
            lt1 = min(Dseg, lt1 + 1.0)
        r[-1] = (lt0, lt1)
        rel = [{"p": words_i[j].get("p", ""),
                "t0": round(max(0.0, r[j][0]), 3),
                "t1": round(min(Dseg, r[j][1]), 3)} for j in range(len(r))]
        out = os.path.join(SENT_NEW, "%d.mp3" % idx).replace("\\", "/")
        subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                       "-i", COMPLETE, "-c", "copy", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur = round(st1 - st0, 3)
        ch1[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0, "t1": dur,
                         "rep": repN, "words": rel}
        print("  idx %2d -> %.2f~%.2fs (%.2fs, %d 词, rep=%d)" %
              (idx, st0, st1, dur, len(rel), repN), flush=True)

    json.dump(ch1, open(os.path.join(AUDIO, "ch1_align.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("ch1_align.json 写出 (%d 句)" % len(ch1), flush=True)

    # 5) 核对之前错配的句(全局词文应与正确文本一致)
    print("\n=== 核对 idx %s 切片内的词文(应分别等于正确文本) ===" % VERIFY_IDX, flush=True)
    for idx in VERIFY_IDX:
        txt = " ".join(w["p"] for w in ch1[str(idx)]["words"][: (len(rules[idx]["words"]) if ch1[str(idx)]["rep"] == 1 else None)])
        # 取一遍的词(去 rep 重复)
        one = ch1[str(idx)]["words"][:len(rules[idx]["words"])]
        print("  idx %d 切片首遍词: %s" % (idx, " ".join(w["p"] for w in one)), flush=True)
        correct = " ".join(o.get("p", "") for o in rules[idx]["words"])
        ok = (" ".join(w["p"] for w in one)) == correct
        print("       正确文本: %s" % correct, flush=True)
        print("       匹配: %s" % ("OK ✓" if ok else "!! 不匹配"), flush=True)

    # 6) 合并回主清单
    print("\n=== 合并回 manifest_audio.js ===", flush=True)
    M.main()


if __name__ == "__main__":
    main()
