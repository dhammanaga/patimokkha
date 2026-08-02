#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用尊者提供的【完整录音】重新制作任意章节(idx 范围由 data.js sections 决定)的音频。

用法:
  python align_ch_generic.py --chapters 2 3 \
      --audio "序20220805_091549.mp3" "巴拉基咖20220808_102156.mp3"

流程(每章):
 1) 解码完整录音, 25s 分块过 ONNX(wav2vec2) + numpy 向量化 CTC Viterbi -> 全部词在整段里的全局时间;
 2) 缓存 chN_align_raw.json;
 3) v4 中点边界法逐句切片 -> sent_new/{idx}.mp3, 写 chN_align.json;
 4) 不修改 app.js; 切片各自独立 clip, t0=0,t1=分句时长, 词时相对分句。

随后请单独运行 merge_align_to_manifest.py 合并回 manifest_audio.js。
"""
import sys, os, json, subprocess, time, shutil, argparse
import numpy as np
SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
SENT_NEW = os.path.join(AUDIO, "sent_new")
NAMO = "namo tassa"
CHUNK = 400000
LEAD = 0.12
TAIL = 0.40
MIN_DUR = 0.6


def emissions_raw(x_chunk, sess):
    x_chunk = x_chunk.astype(np.float32).reshape(1, len(x_chunk))
    mask = np.ones((1, len(x_chunk)), dtype=np.int64)
    out = sess.run(None, {"input_values": x_chunk, "attention_mask": mask})[0]
    return out[0]


def ctc_viterbi(em, target_ids):
    """向量化 CTC Viterbi 强制对齐(等价 FA.ctc_align，但快 ~100x)。"""
    T = em.shape[0]
    K = len(target_ids)
    if K == 0:
        return []
    ext = np.zeros(2 * K + 1, dtype=np.int64)
    for i in range(K):
        ext[2 * i + 1] = target_ids[i]
    S = 2 * K + 1
    alpha = np.full(S, -np.inf)
    alpha[0] = em[0][0]
    if K >= 1:
        alpha[1] = em[0][target_ids[0]]
    phi = np.zeros((T, S), dtype=np.int32)
    idx = np.arange(S)
    for t in range(1, T):
        lab = em[t][ext]
        stay = alpha + lab
        left = np.full(S, -np.inf)
        left[1:] = alpha[:-1]
        left = left + lab
        skip = np.full(S, -np.inf)
        skip[2:] = alpha[:-2]
        skip = np.where(ext == 0, skip, -np.inf)
        best = stay.copy()
        src = idx.copy()
        m = left > best
        best[m] = left[m]
        src[m] = idx[m] - 1
        m2 = skip > best
        best[m2] = skip[m2]
        src[m2] = idx[m2] - 2
        alpha = best
        phi[t] = src
    s = 2 * K if alpha[2 * K] >= alpha[2 * K - 1] else 2 * K - 1
    pos = [-1] * T
    t = T - 1
    while t >= 0:
        if s % 2 == 1:
            pos[t] = (s - 1) // 2
        s = int(phi[t][s])
        t -= 1
    return pos


def align_full(x, D, all_words, vocab, sess):
    x = x - x.mean()
    sd = x.std()
    if sd > 1e-5:
        x = x / sd
    ems = []
    T = len(x)
    for s in range(0, T, CHUNK):
        e = min(T, s + CHUNK)
        ems.append(emissions_raw(x[s:e], sess))
    em = np.concatenate(ems, axis=0)
    em = FA.logsoftmax(em)
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
    Tf = em.shape[0]
    FRAME = FA.STRIDE / FA.SR
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
    res = []
    prev = 0.0
    for wi, cs in enumerate(per_word):
        if not cs:
            res.append((prev, min(D, prev + 0.01)))
            prev = res[-1][1]
            continue
        cpos = [i for i, (c, wj) in enumerate(seq) if wj == wi]
        t0 = min(pt[i] for i in cpos)
        t1 = max(pt[i] for i in cpos)
        if t0 < prev:
            t0 = prev
        if t1 <= t0:
            t1 = min(D, t0 + 0.05)
        res.append((t0, t1))
        prev = t1
    if res:
        res[-1] = (res[-1][0], D)
    return res


def do_align(ch, audio_path, A, B):
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]

    all_words = []
    seg_ranges = []
    for idx in range(A, B + 1):
        orig = rules[idx]["words"]
        repN = 3 if rules[idx].get("pali", "").strip().lower().startswith(NAMO) else 1
        words = [dict(w) for w in orig] * repN
        seg_ranges.append((len(all_words), len(all_words) + len(words)))
        all_words.extend(words)

    CACHE = os.path.join(AUDIO, "ch%d_complete.wav" % ch)
    x, sr = FA.decode_real(audio_path, FFMPEG, APP, CACHE)
    D = len(x) / FA.SR
    print("[ch%d] 完整录音解码: %.2fs, %d 采样, 拼接词数=%d" % (ch, D, len(x), len(all_words)), flush=True)

    t0 = time.time()
    res = align_full(x, D, all_words, vocab, sess)
    print("[ch%d] 整段对齐完成: %.1fs, K=%d" % (ch, time.time() - t0, len(res)), flush=True)
    assert len(res) == len(all_words)

    bounds = {}
    word_global = {}
    for si, idx in enumerate(range(A, B + 1)):
        s, e = seg_ranges[si]
        wseg = res[s:e]
        g0 = min(r[0] for r in wseg)
        g1 = max(r[1] for r in wseg)
        bounds[idx] = (g0, g1)
        word_global[idx] = wseg
        print("  idx %2d : %.3f ~ %.3f  (%.2fs)  词数=%d" % (idx, g0, g1, g1 - g0, len(wseg)), flush=True)

    raw = {"D": D, "bounds": {str(k): list(v) for k, v in bounds.items()},
           "word_global": {str(k): [list(w) for w in v] for k, v in word_global.items()},
           "all_words": all_words, "seg_ranges": seg_ranges}
    RAW = os.path.join(AUDIO, "ch%d_align_raw.json" % ch)
    json.dump(raw, open(RAW, "w", encoding="utf-8"), ensure_ascii=False)
    print("[ch%d] 原始对齐已缓存 -> %s" % (ch, RAW), flush=True)
    return raw


def do_split(ch, A, B, raw, audio_path):
    D = raw["D"]
    wg = {int(k): [tuple(w) for w in v] for k, v in raw["word_global"].items()}
    all_words = raw["all_words"]
    seg_ranges = [tuple(s) for s in raw["seg_ranges"]]

    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]

    has = os.path.isdir(SENT_NEW) and any(os.scandir(SENT_NEW))
    BAK = os.path.join(AUDIO, "sent_new_bak_v4_ch%d_%s" % (ch, time.strftime("%Y%m%d_%H%M%S")))
    if has:
        shutil.copytree(SENT_NEW, BAK)
        print("[ch%d] 已备份旧 sent_new -> %s" % (ch, BAK), flush=True)
    os.makedirs(SENT_NEW, exist_ok=True)

    idxs = list(range(A, B + 1))
    G0 = {i: min(w[0] for w in wg[i]) for i in idxs}
    G1 = {i: max(w[1] for w in wg[i]) for i in idxs}
    start = {i: 0.0 for i in idxs}
    end = {i: 0.0 for i in idxs}
    start[A] = max(0.0, G0[A] - LEAD)
    for i in idxs[1:]:
        start[i] = (G1[i - 1] + G0[i]) / 2.0
    for i in idxs[:-1]:
        end[i] = (G1[i] + G0[i + 1]) / 2.0
    end[B] = min(D, G1[B] + TAIL)
    for i in idxs:
        if end[i] - start[i] < MIN_DUR:
            end[i] = start[i] + max(MIN_DUR, (G1[i] - G0[i]) + 0.3)

    chN = {}
    for si, idx in enumerate(idxs):
        st0, st1 = start[idx], end[idx]
        clip = "audio/sent_new/%d.mp3" % idx
        out = os.path.join(SENT_NEW, "%d.mp3" % idx).replace("\\", "/")
        subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                        "-i", audio_path, "-c", "copy", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur = round(st1 - st0, 3)
        orig = rules[idx]["words"]
        olen = len(orig)
        repN = len(wg[idx]) // olen if olen else 1
        rel = []
        for j, (wt0, wt1) in enumerate(wg[idx]):
            oi = j % olen
            rel.append({"p": orig[oi].get("p", ""),
                        "t0": round(max(0.0, wt0 - st0), 3),
                        "t1": round(min(dur, wt1 - st0), 3)})
        chN[str(idx)] = {"clip": clip, "t0": 0, "t1": dur, "rep": repN, "words": rel}
        print("  [ch%d] idx %2d -> %.2f~%.2fs (%.2fs, %d 词, rep=%d)" %
              (ch, idx, st0, st1, dur, len(rel), repN), flush=True)

    json.dump(chN, open(os.path.join(AUDIO, "ch%d_align.json" % ch), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("[ch%d] ch%d_align.json 写出 (%d 句)" % (ch, ch, len(chN)), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", nargs="+", type=int, required=True)
    ap.add_argument("--audio", nargs="+", required=True, help="与 --chapters 顺序对应的完整录音路径")
    args = ap.parse_args()
    assert len(args.audio) == len(args.chapters), "音频数量须与章节数一致"
    data = FA.load_js(os.path.join(APP, "data.js"))
    sections = data["sections"]
    for i, ch in enumerate(args.chapters):
        sec = sections[ch - 1]
        A, B = sec["ruleStart"], sec["ruleEnd"]
        audio = args.audio[i]
        assert os.path.exists(audio), "完整录音不存在: " + audio
        print("===== 处理第 %d 章 (idx %d-%d) 音频=%s =====" % (ch, A, B, os.path.basename(audio)), flush=True)
        raw = do_align(ch, audio, A, B)
        do_split(ch, A, B, raw, audio)


if __name__ == "__main__":
    main()
