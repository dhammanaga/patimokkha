#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用细粒度静音检测得到的真实句边界, 重建第二章 idx 64-79 的句子时间。
真实静音边界(中心): 145.65 / 151.22 / 154.70 / 158.32 / 160.39 / 162.58 / 164.67
=> 关键: block4 真实 [160.13,164.67]=4.54s(旧错估为3.75s, 导致 77/79 被压成0.10s)
   158.32 是 idx73/74 之间的真实停顿(已验证)。
对齐窗口(紧=真实边界, 杜绝跨块抢跑), 块内孤立强制对齐; 保留 36-63 全局对齐。
每个窗口末句延伸到窗口真实尾, 杜绝截断。
"""
import sys, os, json, time, shutil, subprocess
import numpy as np
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:\Users\dhamm\WorkBuddy\巴帝摩卡背诵\app"
AUDIO = os.path.join(APP, "audio")
SENT_NEW = os.path.join(AUDIO, "sent_new")
CH = 2
AUDIO_SRC = r"C:\Users\dhamm\Documents\dhammanaga\巴帝摩卡诵\巴帝摩卡诵.善吉祥长老\序20220805_091549.mp3"
CHUNK = 400000
TAIL = 0.40
MIN_DUR = 0.6

# (start, end, [idx...])  —— 真实静音锚定的对齐窗口
WINDOWS = [
    (145.91, 150.96, [64, 65, 66, 67, 68]),   # 三连 pucchami 公式(无内部停顿)
    (150.96, 154.49, [69, 70]),               # Nidānuddeso / Sutā kho
    (154.49, 158.32, [71, 72, 73]),           # cattāro ... dve aniyatā
    (158.32, 160.13, [74]),                   # tiṃsa nissaggiyā (孤立, 干净)
    (160.13, 164.67, [75, 76, 77, 78, 79]),   # dvenavuti ... avivadamānehi
]


def emissions_raw(x_chunk, sess):
    x_chunk = x_chunk.astype(np.float32).reshape(1, len(x_chunk))
    mask = np.ones((1, len(x_chunk)), dtype=np.int64)
    out = sess.run(None, {"input_values": x_chunk, "attention_mask": mask})[0]
    return out[0]


def ctc_viterbi(em, target_ids):
    T = em.shape[0]; K = len(target_ids)
    if K == 0:
        return []
    ext = np.zeros(2 * K + 1, dtype=np.int64)
    for i in range(K):
        ext[2 * i + 1] = target_ids[i]
    S = 2 * K + 1
    alpha = np.full(S, -np.inf); alpha[0] = em[0][0]
    if K >= 1:
        alpha[1] = em[0][target_ids[0]]
    phi = np.zeros((T, S), dtype=np.int32)
    idx = np.arange(S)
    for t in range(1, T):
        lab = em[t][ext]
        stay = alpha + lab
        left = np.full(S, -np.inf); left[1:] = alpha[:-1]; left = left + lab
        skip = np.full(S, -np.inf); skip[2:] = alpha[:-2]
        skip = np.where(ext == 0, skip, -np.inf)
        best = stay.copy(); src = idx.copy()
        m = left > best; best[m] = left[m]; src[m] = idx[m] - 1
        m2 = skip > best; best[m2] = skip[m2]; src[m2] = idx[m2] - 2
        alpha = best; phi[t] = src
    s = 2 * K if alpha[2 * K] >= alpha[2 * K - 1] else 2 * K - 1
    pos = [-1] * T; t = T - 1
    while t >= 0:
        if s % 2 == 1:
            pos[t] = (s - 1) // 2
        s = int(phi[t][s]); t -= 1
    return pos


def align_full(x, D, all_words, vocab, sess):
    x = x - x.mean(); sd = x.std()
    if sd > 1e-5:
        x = x / sd
    ems = []
    for s in range(0, len(x), CHUNK):
        e = min(len(x), s + CHUNK)
        ems.append(emissions_raw(x[s:e], sess))
    em = FA.logsoftmax(np.concatenate(ems, axis=0))
    per_word = [FA.norm_word(w.get("p") or w.get("word") or "") for w in all_words]
    seq = []
    for wi, cs in enumerate(per_word):
        for c in cs:
            seq.append((c, wi))
    target_ids = [vocab[c] for c, _ in seq]
    K = len(target_ids)
    if K == 0:
        return [(0.0, D)] * len(all_words)
    pos = ctc_viterbi(em, target_ids)
    Tf = em.shape[0]; FRAME = FA.STRIDE / FA.SR
    frames_of = [[] for _ in range(K)]
    for t in range(Tf):
        if pos[t] >= 0:
            frames_of[pos[t]].append(t)
    pt = [None] * K
    for i in range(K):
        if frames_of[i]:
            pt[i] = (min(frames_of[i]) + max(frames_of[i])) / 2 * FRAME
    known = [i for i in range(K) if pt[i] is not None]
    if not known:
        pt = [D * (i + 1) / (K + 1) for i in range(K)]
    else:
        for i in range(K):
            if pt[i] is None:
                p = max([j for j in known if j < i], default=None)
                n = min([j for j in known if j > i], default=None)
                if p is not None and n is not None:
                    pt[i] = (pt[p] + pt[n]) / 2
                elif p is not None:
                    pt[i] = min(D, pt[p] + 0.15)
                else:
                    pt[i] = max(0.0, pt[n] - 0.15)
    res = []; prev = 0.0
    for wi, cs in enumerate(per_word):
        if not cs:
            res.append((prev, min(D, prev + 0.01))); prev = res[-1][1]; continue
        cpos = [i for i, (c, wj) in enumerate(seq) if wj == wi]
        t0 = min(pt[i] for i in cpos); t1 = max(pt[i] for i in cpos)
        if t0 < prev:
            t0 = prev
        if t1 <= t0:
            t1 = min(D, t0 + 0.05)
        res.append((t0, t1)); prev = t1
    return res


def main():
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    raw = json.load(open(os.path.join(AUDIO, "ch2_align_raw.json"), encoding="utf-8"))
    Bd = raw["bounds"]
    D = raw["D"]

    CACHE = os.path.join(AUDIO, "ch%d_complete.wav" % CH)
    x, sr = FA.decode_real(AUDIO_SRC, FFMPEG, APP, CACHE)
    print("完整解码 %.2fs" % (len(x) / FA.SR), flush=True)

    new_g = {}
    for (bs, be, ids) in WINDOWS:
        all_words = []
        seg = []
        for idx in ids:
            orig = rules[idx]["words"]
            repN = 3 if rules[idx].get("pali", "").strip().lower().startswith("namo tassa") else 1
            words = [dict(w) for w in orig] * repN
            seg.append((len(all_words), len(all_words) + len(words)))
            all_words.extend(words)
        f0 = int(bs * FA.SR); f1 = int(be * FA.SR)
        xw = x[f0:f1].copy(); Dw = len(xw) / FA.SR
        res = align_full(xw, Dw, all_words, vocab, sess)
        assert len(res) == len(all_words)
        off = bs
        for si, idx in enumerate(ids):
            s, e = seg[si]
            wseg = res[s:e]
            ng = [(off + a, off + b) for (a, b) in wseg]
            new_g[idx] = ng
            nw = len(rules[idx]["words"])
            span = ng[-1][1] - ng[0][0]
            dpw = span / nw
            flag = "  <== 抢跑?" if dpw < 0.30 else ""
            print("idx %2d 窗[%.2f,%.2f] 新 %.2f~%.2f (%.2fs, %.2f s/w)%s | %s" % (
                idx, bs, be, ng[0][0], ng[-1][1], span, dpw, flag,
                (rules[idx].get('pali') or '')[:24]))

    all_ids = [i for (_, _, ids) in WINDOWS for i in ids]
    G0 = {i: min(w[0] for w in new_g[i]) for i in all_ids}
    G1 = {i: max(w[1] for w in new_g[i]) for i in all_ids}
    start = {i: 0.0 for i in all_ids}; end = {i: 0.0 for i in all_ids}
    # 窗口内中点拼接; 每窗口首句从窗口真实起点起, 末句延伸到窗口真实尾
    for (bs, be, ids) in WINDOWS:
        for k, idx in enumerate(ids):
            if k == 0:
                start[idx] = max(0.0, bs - 0.05)
            else:
                start[idx] = (G1[ids[k-1]] + G0[idx]) / 2.0
            if k == len(ids) - 1:
                end[idx] = min(D, be + 0.05)
            else:
                end[idx] = (G1[idx] + G0[ids[k+1]]) / 2.0
    for i in all_ids:
        if end[i] - start[i] < MIN_DUR:
            end[i] = start[i] + max(MIN_DUR, (G1[i] - G0[i]) + 0.3)

    BAK = os.path.join(AUDIO, "ch%d_align_raw.bak_seg_%s.json" % (CH, time.strftime("%Y%m%d_%H%M%S")))
    shutil.copy(os.path.join(AUDIO, "ch%d_align_raw.json" % CH), BAK)
    for idx in all_ids:
        Bd[str(idx)] = [new_g[idx][0][0], new_g[idx][-1][1]]
        raw["word_global"][str(idx)] = [[round(a, 3), round(b, 3)] for (a, b) in new_g[idx]]
    json.dump(raw, open(os.path.join(AUDIO, "ch%d_align_raw.json" % CH), "w", encoding="utf-8"), ensure_ascii=False)

    has = os.path.isdir(SENT_NEW) and any(os.scandir(SENT_NEW))
    BAK2 = os.path.join(AUDIO, "sent_new_bak_seg_%s" % time.strftime("%Y%m%d_%H%M%S"))
    if has:
        shutil.copytree(SENT_NEW, BAK2); print("备份 sent_new ->", BAK2, flush=True)
    os.makedirs(SENT_NEW, exist_ok=True)

    chN = json.load(open(os.path.join(AUDIO, "ch%d_align.json" % CH), encoding="utf-8"))
    for idx in all_ids:
        st0, st1 = start[idx], end[idx]
        out = os.path.join(SENT_NEW, "%d.mp3" % idx).replace("\\", "/")
        subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                        "-i", AUDIO_SRC, "-c", "copy", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur = round(st1 - st0, 3)
        orig = rules[idx]["words"]; olen = len(orig)
        # 逐词时间: 罗马字字符数加权, 在本句真实时长[0,dur]内铺开。
        # aligner 对公式句末词常给零宽(抢跑), 故不依赖其相对间距, 改用稳健的字符加权,
        # 保证每词都有合理时长(无坏词/零宽), 长词占更多时间(贴近实际念诵)。
        weights = [max(1, len((orig[oi].get("p") or "").strip())) for oi in range(olen)]
        total_w = sum(weights)
        rel = []
        cursor = 0.0
        for oi in range(olen):
            wlen = dur * weights[oi] / total_w
            t0 = round(cursor, 3)
            t1 = round(min(dur, cursor + wlen), 3)
            if t1 <= t0:
                t1 = min(dur, t0 + 0.05)
            rel.append({"p": orig[oi].get("p", ""), "t0": t0, "t1": t1})
            cursor = t1
        chN[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0, "t1": dur, "rep": 1, "words": rel}
        # 坏数据自检
        bad = [w for w in rel if w["t1"] - w["t0"] < 0.10]
        warn = "  !! 坏词%d" % len(bad) if bad else ""
        print("  切片 idx %2d %.2f~%.2fs (%.2fs, %d词)%s" % (idx, st0, st1, dur, len(rel), warn), flush=True)
    json.dump(chN, open(os.path.join(AUDIO, "ch%d_align.json" % CH), "w", encoding="utf-8"), ensure_ascii=False)
    print("ch%d_align.json 已更新 (%d-%d)" % (CH, all_ids[0], all_ids[-1]), flush=True)
    print("备份: %s | %s" % (BAK, BAK2), flush=True)


if __name__ == "__main__":
    main()
