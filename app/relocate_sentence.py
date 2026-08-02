#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用源录音重新定位单个句子(ch,idx)的真实边界与词时(逐句独立对齐)。
替代可能已漂移的 chN_align_raw.bounds。以 data.js 该句正确文字为准。
- 窗口: bounds 里 [G1_prev, G0_next] 略扩 → 只含本句槽位, 避免公式句错配到邻居
- 对窗口解码源 → 该句文字 ctc 对齐 → 得源秒级 [start,end] 与每词语音结束
- 尊者原则: start 往前含上句尾音一点, end 到本句末词真实结束+余量
用法: python relocate_sentence.py --ch 1 --idx 13 [--print]
输出: 打印该句源秒边界; 并写 audio/relocate_{idx}.json
"""
import os, json, re, sys, subprocess
import numpy as np

SKILL = r"C:\Users\dhamm\.workbuddy\skills\pali-forced-align\scripts"
if SKILL not in sys.path:
    sys.path.insert(0, SKILL)
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
sys.path.insert(0, AUDIO)
from _ch_src_map import CH_SRC
LEAD = 0.15          # 本句相对末前一个词的左扩(含上句尾音/首词前)
END_PAD = 0.25       # 本句末词真实结束后余量


def load_js(p):
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.\w+\s*=\s*", "", s, count=1, flags=re.S)
    return s.rstrip().rstrip(";")


def decode_to_pcm(src, s0, s1):
    """解码源 [s0,s1) 为 16k pcm。"""
    tmp = os.path.join(AUDIO, "_reloc_tmp.wav")
    subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % s0, "-to", "%.3f" % s1,
                    "-i", src, "-ar", "16000", "-ac", "1", "-f", "wav", tmp],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    import wave
    w = wave.open(tmp, "rb")
    n = w.getnframes()
    x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    w.close(); os.remove(tmp)
    return x


def align_text_on_pcm(x, text_words, vocab, sess):
    """把文字词序列对齐到 pcm, 返回每词 (t0,t1) 相对窗口起点(秒)."""
    per_word = [FA.norm_word(w) for w in text_words]
    seq = []
    for wi, cs in enumerate(per_word):
        for c in cs:
            seq.append((c, wi))
    target_ids = [vocab[c] for c, _ in seq]
    if not target_ids:
        return [(0.0, len(x) / FA.SR)] * len(per_word)
    em = FA.logsoftmax(FA.emissions(x, sess))
    pos = FA.ctc_align(em, target_ids)
    T = em.shape[0]
    frames_of = [[] for _ in range(len(target_ids))]
    for t in range(T):
        if pos[t] >= 0:
            frames_of[pos[t]].append(t)
    pt = [None] * len(target_ids)
    for i in range(len(target_ids)):
        if frames_of[i]:
            pt[i] = (min(frames_of[i]) + max(frames_of[i])) / 2 * FA.FRAME
    known = [i for i in range(len(target_ids)) if pt[i] is not None]
    D = len(x) / FA.SR
    if not known:
        pt = [D * (i + 1) / (len(target_ids) + 1) for i in range(len(target_ids))]
    else:
        for i in range(len(target_ids)):
            if pt[i] is None:
                p = max([j for j in known if j < i], default=None)
                n = min([j for j in known if j > i], default=None)
                if p is not None and n is not None:
                    pt[i] = (pt[p] + pt[n]) / 2
                elif p is not None:
                    pt[i] = min(D, pt[p] + 0.15)
                else:
                    pt[i] = max(0.0, pt[n] - 0.15)
    # 聚合到词
    res = []
    for wi, cs in enumerate(per_word):
        cpos = [i for i, (c, wj) in enumerate(seq) if wj == wi]
        if not cpos:
            res.append((0.0, 0.0)); continue
        t0 = min(pt[i] for i in cpos); t1 = max(pt[i] for i in cpos)
        res.append((t0, t1))
    # 单调化
    prev = 0.0
    for i in range(len(res)):
        if res[i][1] > 0 and res[i][0] < prev:
            res[i] = (prev, max(prev + 0.01, res[i][1]))
        prev = max(prev, res[i][1])
    return res


def main():
    args = sys.argv[1:]
    ch = int(args[args.index("--ch") + 1])
    idx = int(args[args.index("--idx") + 1])
    do_print = "--print" in args
    data = json.loads(load_js(os.path.join(APP, "data.js")))
    rule = data["rules"][idx]
    wds = [w.get("p", "") for w in rule.get("words", [])]
    src = CH_SRC.get(ch)
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    # 用 bounds 取本句槽位窗口
    rawp = os.path.join(AUDIO, "ch%d_align_raw.json" % ch)
    raw = json.load(open(rawp, encoding="utf-8"))
    b = {int(k): tuple(v) for k, v in raw["bounds"].items()}
    idxs = sorted(b); p_i = idxs.index(idx)
    G1prev = b[idxs[p_i - 1]][1] if p_i > 0 else max(0, b[idx][0] - 4)
    G0next = b[idxs[p_i + 1]][0] if p_i < len(idxs) - 1 else raw.get("D", b[idx][1] + 4)
    w0 = max(0, G1prev - 0.5)   # 窗内本句槽起
    w1 = min(raw.get("D", 1e9), G0next + 0.5)
    if w1 - w0 < 2.0:  # 窗太窄扩到 2s
        w0 = max(0, b[idx][0] - 1.0); w1 = b[idx][1] + 1.0
    x = decode_to_pcm(src, w0, w1)
    rel = align_text_on_pcm(x, wds, vocab, sess)
    # 句子边界 = 首词t0 - LEAD  .. 末词t1(强制到真实结束) + END_PAD
    if not rel:
        print("对齐失败"); return
    t0 = min(r[0] for r in rel if r[1] > 0)
    t1 = max(r[1] for r in rel)
    start = max(0, w0 + t0 - LEAD)
    end = min(raw.get("D", 1e9), w0 + t1 + END_PAD)
    out = dict(ch=ch, idx=idx, src_start=round(start, 3), src_end=round(end, 3),
               w0=round(w0, 3), w1=round(w1, 3),
               words=[{"p": wds[i], "t0": round(w0 + r[0], 3), "t1": round(w0 + r[1], 3)}
                      for i, r in enumerate(rel)])
    json.dump(out, open(os.path.join(AUDIO, "relocate_%d.json" % idx), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("ch%d idx%d [%s] 源边界: %.3f ~ %.3f (%.2fs)" % (ch, idx, wds[0][:12], start, end, end - start))
    for wi, r in enumerate(rel):
        print("   %-22s %.3f ~ %.3f" % (wds[wi][:20], w0 + r[0], w0 + r[1]))


if __name__ == "__main__":
    main()
