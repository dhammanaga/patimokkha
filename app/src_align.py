#!/usr/bin/env python
"""将句子文字对源录音的某窗口做词级强制对齐(CTC), 得到每词在源里的精确起止。
用于修复"公式区对齐漂移": 在源的大致窗口里精确定位每句真实边界。
用法: python src_align.py --ch 2 --idx 64 --w0 135.5 --w1 141.0
"""
import subprocess, numpy as np, sys, json, re, os

APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SR = 16000

_CH_SRC = {
    1: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/巴帝摩卡诵.善吉祥长老/事前任务20220801_085203.mp3",
    2: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/巴帝摩卡诵.善吉祥长老/序20220805_091549.mp3",
    3: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/巴帝摩卡诵.善吉祥长老/巴拉基咖20220808_102156.mp3",
    4: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/4. Sanghadisesuddeso.mp3",
    5: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/5. Aniyatuddeso.mp3",
    6: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/6. Timsa Nissaggiya Pacittiya Dhamma.mp3",
    7: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/7. Dvenavuti Pacittiya Dhamma.mp3",
    8: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/8. Cattaro Patidesaniya Dhamm.mp3",
    9: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/9. Sekhiya Dhamma.mp3",
    10: r"C:/Users/dhamm/Documents/dhammanaga/巴帝摩卡诵/善巧提供/后7章/10. Satta Adhikarana Samatha Dhamma.mp3",
}

def load_js(path, var):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.%s\s*=\s*" % var, "", s, count=1, flags=re.S)
    s = s.rstrip().rstrip(";")
    return json.loads(s)

def align_window(sess, vocab, src, t0, t1, words):
    """对齐整句文字到源窗口[t0,t1], 返回每词(词, rel_t0, rel_t1, 源g0, 源g1)."""
    p = subprocess.run([FFMPEG, "-y", "-ss", "%.3f" % t0, "-to", "%.3f" % t1, "-i", src,
                        "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    D = len(x) / SR
    em = FA.logsoftmax(FA.emissions(x, sess))
    per_word = [FA.norm_word(w) for w in words]
    seq = [(c, wi) for wi, cs in enumerate(per_word) for c in cs]
    if not seq:
        return [(w, 0.0, 0.0, t0, t1) for w in words]
    target_ids = [vocab[c] for c, _ in seq]
    pos = FA.ctc_align(em, target_ids)
    T = em.shape[0]
    frames = [[] for _ in range(len(target_ids))]
    for t in range(T):
        if pos[t] >= 0:
            frames[pos[t]].append(t)
    pt = [None] * len(target_ids)
    for i, f in enumerate(frames):
        if f:
            pt[i] = (min(f) + max(f)) / 2 * FA.FRAME
    # 插值 None
    known = [i for i in range(len(target_ids)) if pt[i] is not None]
    if known:
        for i in range(len(target_ids)):
            if pt[i] is None:
                p_p = max([j for j in known if j < i], default=None)
                n_p = min([j for j in known if j > i], default=None)
                if p_p is not None and n_p is not None:
                    pt[i] = (pt[p_p] + pt[n_p]) / 2
                elif p_p is not None:
                    pt[i] = min(D, pt[p_p] + 0.1)
                else:
                    pt[i] = max(0.0, pt[n_p] - 0.1)
    else:
        pt = [D * (i + 1) / (len(target_ids) + 1) for i in range(len(target_ids))]
    res = []
    prev = 0.0
    for wi, cs in enumerate(per_word):
        if not cs:
            res.append((words[wi], prev, min(D, prev + 0.01), t0 + prev, t0 + min(D, prev + 0.01)))
            prev = res[-1][2]
            continue
        cpos = [i for i, (c, wj) in enumerate(seq) if wj == wi]
        t0w = min(pt[i] for i in cpos)
        t1w = max(pt[i] for i in cpos)
        if t0w < prev:
            t0w = prev
        if t1w <= t0w:
            t1w = min(D, t0w + 0.05)
        res.append((words[wi], round(t0w, 3), round(t1w, 3), round(t0 + t0w, 3), round(t0 + t1w, 3)))
        prev = t1w
    return res

def main():
    args = sys.argv[1:]
    def arg(name, default=None):
        if "--%s" % name in args:
            return args[args.index("--%s" % name) + 1]
        return default
    ch = int(arg("ch", "2"))
    idx = int(arg("idx", "64"))
    w0 = float(arg("w0", "0"))
    w1 = float(arg("w1", "10"))
    verbose = "--v" in args
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = load_js(os.path.join(APP, "data.js"), "PATIMOKKHA_DATA")
    rule = data["rules"][idx]
    words = rule.get("words") or []
    wlist = [w.get("p") or w.get("word") for w in words if w.get("p") or w.get("word")]
    if not wlist:
        # 从 pali 拆词
        wlist = [w for w in re.split(r"\s+", rule.get("pali", "").strip())]
    src = _CH_SRC.get(ch)
    res = align_window(sess, vocab, src, w0, w1, wlist)
    print("== ch%d idx%d [%s, %s] %s ==" % (ch, idx, w0, w1, rule.get("pali", "")[:50]))
    gs, ge = res[0][3], res[-1][4]
    print("  句子起止(源): %.3f ~ %.3f  扩展建议: %.3f ~ %.3f" % (gs, ge, max(0.0, gs - 0.15), ge + 0.4))
    for w, rt0, rt1, g0, g1 in res:
        print("    %-24s rel[%.3f,%.3f] 源[%.3f,%.3f]" % (w, rt0, rt1, g0, g1))

if __name__ == "__main__":
    main()
