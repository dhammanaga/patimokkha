#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用尊者提供的【完整录音】重新制作第1章(事前任务, idx 0-35)的音频。

流程：
 1) 解码完整录音，按 25s 分块过 wav2vec2 模型(避免 ONNX OOM)，拼接声学特征；
 2) 对"全部 36 句词(含 Namo x3)拼成的长文本"在整段特征上做全局 CTC Viterbi
    -> 每个词在完整录音里的全局时间；
 3) 缓存原始对齐结果(ch1_align_raw.json)，切分失败也不重算；
 4) 用 ffmpeg -c copy 按边界切回 36 个分句 mp3(覆盖旧 sent_new/*.mp3，先备份)；
 5) 输出 ch1_align.json(与第2-11章同格式)。

不修改 app.js：分句 mp3 各自独立成 clip，t0=0, t1=分句时长，词时相对分句。
"""
import sys, os, json, subprocess, time, shutil
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
COMPLETE = r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/巴帝摩卡诵.善吉祥长老/事前任务20220801_085203.mp3"
CACHE = r"E:/WorkBuddy/.fa_cache/_ch1_complete.wav"
SENT_NEW = os.path.join(AUDIO, "sent_new")
RAW = os.path.join(AUDIO, "ch1_align_raw.json")
LEAD = 0.12
TAIL = 0.25
NAMO = "namo tassa"
CHUNK = 400000   # 25s @16k


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
    INF = -1e30
    for t in range(1, T):
        lab = em[t][ext]                     # 各状态的标签概率
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


def do_align():
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]
    sec0 = data["sections"][0]
    A, B = sec0["ruleStart"], sec0["ruleEnd"]

    all_words = []
    seg_ranges = []
    for idx in range(A, B + 1):
        orig = rules[idx]["words"]
        repN = 3 if rules[idx].get("pali", "").strip().lower().startswith(NAMO) else 1
        words = [dict(w) for w in orig] * repN
        seg_ranges.append((len(all_words), len(all_words) + len(words)))
        all_words.extend(words)

    x, sr = FA.decode_real(COMPLETE, FFMPEG, APP, CACHE)
    D = len(x) / FA.SR
    print("完整录音解码: %.2fs, %d 采样, 拼接词数=%d" % (D, len(x), len(all_words)), flush=True)

    t0 = time.time()
    res = align_full(x, D, all_words, vocab, sess)
    print("整段对齐完成: %.1fs, K=%d" % (time.time() - t0, len(res)), flush=True)
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
    json.dump(raw, open(RAW, "w", encoding="utf-8"), ensure_ascii=False)
    print("原始对齐已缓存 ->", RAW, flush=True)
    return raw


def do_split(raw):
    D = raw["D"]
    bounds = {int(k): tuple(v) for k, v in raw["bounds"].items()}
    word_global = {int(k): [tuple(w) for w in v] for k, v in raw["word_global"].items()}
    all_words = raw["all_words"]
    seg_ranges = [tuple(s) for s in raw["seg_ranges"]]

    data = FA.load_js(os.path.join(APP, "data.js"))
    rules = data["rules"]

    has_files = os.path.isdir(SENT_NEW) and any(os.scandir(SENT_NEW))
    BAK = os.path.join(AUDIO, "sent_new_bak_before_complete_%s" % time.strftime("%Y%m%d_%H%M%S"))
    if has_files:
        shutil.copytree(SENT_NEW, BAK)
        print("已备份旧 sent_new ->", BAK, flush=True)
    os.makedirs(SENT_NEW, exist_ok=True)

    ch1 = {}
    for si, idx in enumerate(range(0, 36)):
        g0, g1 = bounds[idx]
        st0 = max(0.0, g0 - LEAD)
        st1 = min(D, g1 + TAIL)
        out = os.path.join(SENT_NEW, "%d.mp3" % idx).replace("\\", "/")
        subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % st0, "-to", "%.3f" % st1,
                        "-i", COMPLETE, "-c", "copy", out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        # 实际时长(ffprobe)
        dur = get_duration(out)
        if dur is None:
            dur = round(st1 - st0, 3)
        repN = 3 if rules[idx].get("pali", "").strip().lower().startswith(NAMO) else 1
        wseg = word_global[idx]
        s, e = seg_ranges[si]
        rel_words = []
        for j, (wt0, wt1) in enumerate(wseg):
            p = all_words[s + j].get("p", "")
            rel_words.append({"p": p,
                             "t0": round(max(0.0, wt0 - st0), 3),
                             "t1": round(min(dur, wt1 - st0), 3)})
        ch1[str(idx)] = {"clip": "audio/sent_new/%d.mp3" % idx,
                         "t0": 0, "t1": round(dur, 3), "rep": repN, "words": rel_words}
        print("  写出 idx %2d -> sent_new/%d.mp3 (%.2fs, %d 词)" % (idx, idx, dur, len(rel_words)), flush=True)

    json.dump(ch1, open(os.path.join(AUDIO, "ch1_align.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("ch1_align.json 已写出 (%d 句)" % len(ch1), flush=True)


def get_duration(path):
    try:
        out = subprocess.run([FFMPEG.replace("ffmpeg.exe", "ffprobe.exe"), "-v", "error",
                              "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout.decode().strip()
        return float(out)
    except Exception:
        return None


def main():
    assert os.path.exists(COMPLETE), "完整录音不存在: " + COMPLETE
    if os.path.exists(RAW):
        print("发现缓存原始对齐，直接加载(跳过 10 分钟对齐)", flush=True)
        raw = json.load(open(RAW, encoding="utf-8"))
    else:
        raw = do_align()
    do_split(raw)


if __name__ == "__main__":
    main()
