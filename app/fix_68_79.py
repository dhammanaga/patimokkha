#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""针对性修复第二章 idx 68-79(仅 68/69/70 被模型抢跑压坏), 保留 36-67 全局对齐。

修法: 对 68-79 每句单独在[全局位置-1.0, 全局位置+5.0]窗口内只对齐该句词(无末尾强制拉伸 bug),
再 v4 中点链式拼接 68-79 并重切片。左锚点用全局可靠的 idx 67 结束时间。
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
A, B = 68, 79
ANCHOR_L = 67
AUDIO_SRC = r"C:\Users\dhamm\Documents\dhammanaga\巴帝摩卡诵\巴帝摩卡诵.善吉祥长老\序20220805_091549.mp3"
CHUNK = 400000
TAIL = 0.40
MIN_DUR = 0.6
WIN_LO = 1.0
WIN_HI = 5.0


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
    return res   # 注意: 不强制 res[-1]=(...,D), 避免单句被拉到窗口尾


def main():
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]

    raw = json.load(open(os.path.join(AUDIO, "ch2_align_raw.json"), encoding="utf-8"))
    Bd = raw["bounds"]
    G1_L = Bd[str(ANCHOR_L)][1]   # 全局可靠锚点 idx67 结束
    D = raw["D"]

    CACHE = os.path.join(AUDIO, "ch%d_complete.wav" % CH)
    x, sr = FA.decode_real(AUDIO_SRC, FFMPEG, APP, CACHE)
    print("完整解码 %.2fs" % (len(x) / FA.SR), flush=True)

    new_g = {}
    prev_end = G1_L   # 顺序非重叠: 每句窗口紧接上一句结束, 强制时间顺序, 杜绝重叠
    for idx in range(A, B + 1):
        orig = rules[idx]["words"]
        repN = 3 if rules[idx].get("pali", "").strip().lower().startswith("namo tassa") else 1
        words = [dict(w) for w in orig] * repN
        nw = len(orig)
        est = nw * 0.9 + 1.5
        win0 = prev_end - 0.2
        win1 = min(D + 0.2, prev_end + est)
        f0 = int(win0 * FA.SR); f1 = int(win1 * FA.SR)
        xw = x[f0:f1].copy()
        Dw = len(xw) / FA.SR
        res = align_full(xw, Dw, words, vocab, sess)
        assert len(res) == len(words)
        ng = [(win0 + a, win0 + b) for (a, b) in res]
        new_g[idx] = ng
        prev_end = ng[-1][1]
        dpw = (ng[-1][1] - ng[0][0]) / nw
        print("idx %2d 窗口[%.2f,%.2f] 新 %.2f~%.2f (%.2fs, %.2f s/w) | %s" % (
            idx, win0, win1, ng[0][0], ng[-1][1], ng[-1][1]-ng[0][0], dpw,
            (rules[idx].get('pali') or '')[:24]))

    print("\n=== 链式拼接 ===")
    idxs = list(range(A, B + 1))
    G0 = {i: min(w[0] for w in new_g[i]) for i in idxs}
    G1 = {i: max(w[1] for w in new_g[i]) for i in idxs}
    start = {i: 0.0 for i in idxs}; end = {i: 0.0 for i in idxs}
    start[A] = (G1_L + G0[A]) / 2.0
    for i in idxs[1:]:
        start[i] = (G1[i-1] + G0[i]) / 2.0
    for i in idxs[:-1]:
        end[i] = (G1[i] + G0[i+1]) / 2.0
    end[B] = min(D, G1[B] + TAIL)
    for i in idxs:
        if end[i] - start[i] < MIN_DUR:
            end[i] = start[i] + max(MIN_DUR, (G1[i] - G0[i]) + 0.3)

    BAK = os.path.join(AUDIO, "ch%d_align_raw.bak_6879_%s.json" % (CH, time.strftime("%Y%m%d_%H%M%S")))
    shutil.copy(os.path.join(AUDIO, "ch%d_align_raw.json" % CH), BAK)
    for idx in idxs:
        Bd[str(idx)] = [new_g[idx][0][0], new_g[idx][-1][1]]
        raw["word_global"][str(idx)] = [[round(a, 3), round(b, 3)] for (a, b) in new_g[idx]]
    json.dump(raw, open(os.path.join(AUDIO, "ch%d_align_raw.json" % CH), "w", encoding="utf-8"), ensure_ascii=False)

    has = os.path.isdir(SENT_NEW) and any(os.scandir(SENT_NEW))
    BAK2 = os.path.join(AUDIO, "sent_new_bak_6879_%s" % time.strftime("%Y%m%d_%H%M%S"))
    if has:
        shutil.copytree(SENT_NEW, BAK2); print("备份 sent_new ->", BAK2, flush=True)
    os.makedirs(SENT_NEW, exist_ok=True)

    chN = json.load(open(os.path.join(AUDIO, "ch%d_align.json" % CH), encoding="utf-8"))
    for idx in idxs:
        st0, st1 = start[idx], end[idx]
        out = os.path.join(SENT_NEW, "%d.mp3" % idx).replace("\\", "/")
        subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                        "-i", AUDIO_SRC, "-c", "copy", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur = round(st1 - st0, 3)
        orig = rules[idx]["words"]; olen = len(orig)
        wseg = [(a, b) for (a, b) in new_g[idx]]
        rel = []
        for j, (wt0, wt1) in enumerate(wseg):
            oi = j % olen
            rel.append({"p": orig[oi].get("p", ""),
                        "t0": round(max(0.0, wt0 - st0), 3),
                        "t1": round(min(dur, wt1 - st0), 3)})
        chN[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx, "t0": 0, "t1": dur, "rep": 1, "words": rel}
        print("  切片 idx %2d %.2f~%.2fs (%.2fs, %d 词)" % (idx, st0, st1, dur, len(rel)), flush=True)
    json.dump(chN, open(os.path.join(AUDIO, "ch%d_align.json" % CH), "w", encoding="utf-8"), ensure_ascii=False)
    print("ch%d_align.json 已更新 (%d-%d)" % (CH, A, B), flush=True)
    print("备份: %s | %s" % (BAK, BAK2), flush=True)


if __name__ == "__main__":
    main()
