#!/usr/bin/env python
"""对源公式区做"整段句子序列"词级强制对齐, 返回每个词在源里的精确位置。
比单句窄窗口更稳(因顺序约束), 避免"窗口截断首词"和"相似句ctc错配"。
用法: python seq_align.py --ch 2 --idxs 64,65,66,67,68,69 --w0 133 --w1 166
"""
import subprocess, numpy as np, sys, json, re, os

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
sys.path.insert(0, APP)
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"

_CH_SRC = {
    1: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/巴帝摩卡诵.善吉祥长老/事前任务20220801_085203.mp3",
    2: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/巴帝摩卡诵.善吉祥长老/序20220805_091549.mp3",
    3: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/巴帝摩卡诵.善吉祥长老/巴拉基咖20220808_102156.mp3",
    4: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/4. Sanghadisesuddeso.mp3",
}

def load_js(path, var):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.%s\s*=\s*" % var, "", s, count=1, flags=re.S)
    return json.loads(s.rstrip().rstrip(";"))

def align_seq(sess, vocab, src, t0, t1, words, sent_bounds):
    """words: 扁平词列表; sent_bounds: [(start_word_idx, end_word_idx)] 各句词索引区间.
    对齐整段, 返回每词(词, 源t0, 源t1).
    """
    p = subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % t0, "-to", "%.3f" % t1, "-i", src,
                        "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    em = FA.logsoftmax(FA.emissions(x, sess))
    per_word = [FA.norm_word(w) for w in words]
    seq = [(c, i) for i, cs in enumerate(per_word) for c in cs]
    if not seq:
        return []
    target_ids = [vocab[c] for c, _ in seq]
    pos = FA.ctc_align(em, target_ids)
    T = em.shape[0]
    frames = [[] for _ in range(len(target_ids))]
    for tt in range(T):
        if pos[tt] >= 0:
            frames[pos[tt]].append(tt)
    pt = [None] * len(target_ids)
    for i, f in enumerate(frames):
        if f:
            pt[i] = (min(f) + max(f)) / 2 * FA.FRAME
    known = [i for i in range(len(target_ids)) if pt[i] is not None]
    if known:
        for i in range(len(target_ids)):
            if pt[i] is None:
                pp = max([j for j in known if j < i], default=None)
                nn = min([j for j in known if j > i], default=None)
                if pp is not None and nn is not None:
                    pt[i] = (pt[pp] + pt[nn]) / 2
                elif pp is not None:
                    pt[i] = pt[pp] + 0.05
                elif nn is not None:
                    pt[i] = max(0.0, pt[nn] - 0.05)
    else:
        pt = [t1 * (i + 1) / (len(target_ids) + 1) for i in range(len(target_ids))]
    # 每词起止 = 该词所有char的min/max源时间
    res = []
    char_idx = 0
    word_times = []
    for i, cs in enumerate(per_word):
        if not cs:
            word_times.append((pt[char_idx - 1] if char_idx else 0.0, pt[char_idx - 1] if char_idx else 0.0))
            continue
        c_ids = [char_idx + j for j in range(len(cs))]
        pts = [pt[c] for c in c_ids]
        w0 = min(pts); w1 = max(pts)
        if w1 <= w0:
            w1 = w0 + 0.02
        word_times.append((t0 + w0, t0 + w1))
        char_idx += len(cs)
    # 强制单调
    prev = -1e9
    for i in range(len(word_times)):
        a, b = word_times[i]
        if a < prev:
            a = prev; b = max(a + 0.01, b)
        if b < a:
            b = a + 0.02
        word_times[i] = (a, b)
        prev = b
    return word_times

def main():
    args = sys.argv[1:]
    def arg(name, default=None):
        if "--%s" % name in args:
            return args[args.index("--%s" % name) + 1]
        return default
    ch = int(arg("ch", "2"))
    idxs = [int(x) for x in arg("idxs", "64,65,66,67,68,69").split(",")]
    w0 = float(arg("w0", "0")); w1 = float(arg("w1", "10"))
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = load_js(os.path.join(APP, "data.js"), "PATIMOKKHA_DATA")
    all_words = []
    sent_widx = []  # (start,end) 各句在 all_words 的区间
    for idx in idxs:
        rule = data["rules"][idx]
        wl = [w.get("p") or w.get("word") for w in rule.get("words", []) if w.get("p")]
        if not wl:
            wl = [w for w in re.split(r"\s+", rule.get("pali", "").strip()) if w]
        s_i = len(all_words)
        all_words.extend(wl)
        sent_widx.append((s_i, len(all_words)) if wl else (s_i, s_i))
    wt = align_seq(sess, vocab, _CH_SRC[ch], w0, w1, all_words, sent_widx)
    print("== ch%d 公式区序列对齐 [%s,%s] ==" % (ch, w0, w1))
    # 按句切分输出
    for k, (idx, (ws, we)) in enumerate(zip(idxs, sent_widx)):
        sg = wt[ws:we] if we > ws else []
        if sg:
            g0 = sg[0][0]; g1 = sg[-1][1]
            print("  idx%d: 源[%.3f, %.3f] 扩展[%.3f, %.3f]" % (idx, g0, g1, max(0, g0 - 0.35), g1 + 0.5))
            for w, (a, b) in zip(all_words[ws:we], sg):
                print("      %-26s 源[%.3f, %.3f]" % (w, a, b))
        else:
            print("  idx%d: (无词)" % idx)

if __name__ == "__main__":
    main()
