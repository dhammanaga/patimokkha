#!/usr/bin/env python
"""对指定 idx 的 clip 文件, 用 data.rules[idx].words 在 clip 内做词级对齐, 重写 manifest.words。
用于修复"重编号后 manifest.words 与 data.js 错位"(逐词点读错)。
用法: python rebuild_words.py --idx 80,81,82,83  (或 --ch 3 整个章节)
"""
import subprocess, numpy as np, sys, os, json, re, time
APP = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵/app"
AUDIO = os.path.join(APP, "audio")
sys.path.insert(0, APP)
sys.path.insert(0, r"C:/Users/dhamm/.workbuddy/skills/pali-forced-align/scripts")
import src_align as SA
import forced_align as FA

MODEL = r"E:/WorkBuddy/.fa_cache/model.onnx"
VOCAB = r"E:/WorkBuddy/.fa_cache/repo/vocab.json"
FFMPEG = r"C:/Users/dhamm/AppData/Roaming/kingsoft/wps/addons/pool/win-i386/kaudio_3.1.0.9646/ffmpeg.exe"
SR = 16000

def load_js(path, var):
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"^.*?window\.%s\s*=\s*" % var, "", s, count=1, flags=re.S)
    return json.loads(s.rstrip().rstrip(";"))

def clip_dur_mono(path):
    """解码 clip 为 16k 单声道, 返回(x: float32 array, dur_sec)."""
    p = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", path, "-ar", "16000",
                        "-ac", "1", "-f", "s16le", "-"], stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=30)
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return x, len(x) / SR

def align_clip_words(sess, vocab, clip_path, words):
    """在 clip 内对齐 words, 返回每词 rel [t0,t1]."""
    x, D = clip_dur_mono(clip_path)
    if len(x) < 1600 * 0.3:
        return None, D
    em = FA.logsoftmax(FA.emissions(x, sess))
    per_word = [FA.norm_word(w) for w in words]
    seq = [(c, wi) for wi, cs in enumerate(per_word) for c in cs]
    if not seq:
        return [(0.0, D)] * len(words), D
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
    known = [i for i in range(len(target_ids)) if pt[i] is not None]
    if known:
        for i in range(len(target_ids)):
            if pt[i] is None:
                pp = max([j for j in known if j < i], default=None)
                nn = min([j for j in known if j > i], default=None)
                if pp is not None and nn is not None:
                    pt[i] = (pt[pp] + pt[nn]) / 2
                elif pp is not None:
                    pt[i] = min(D, pt[pp] + 0.08)
                elif nn is not None:
                    pt[i] = max(0.0, pt[nn] - 0.08)
    else:
        pt = [D * (i + 1) / (len(target_ids) + 1) for i in range(len(target_ids))]
    res = []; prev = 0.0
    for wi, cs in enumerate(per_word):
        if not cs:
            res.append((prev, min(D, prev + 0.01))); prev = res[-1][1]; continue
        cpos = [i for i, (c, wj) in enumerate(seq) if wj == wi]
        t0 = min(pt[i] for i in cpos); t1 = max(pt[i] for i in cpos)
        if t0 < prev: t0 = prev
        if t1 <= t0: t1 = min(D, t0 + 0.05)
        res.append((t0, t1)); prev = t1
    return res, D

def main():
    args = sys.argv[1:]
    def arg(name, default=None):
        if "--%s" % name in args:
            return args[args.index("--%s" % name) + 1]
        return default
    idx_str = arg("idx")
    ch_str = arg("ch")
    vocab = json.load(open(VOCAB, encoding="utf-8"))
    sess = FA.ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    data = load_js(os.path.join(APP, "data.js"), "PATIMOKKHA_DATA")
    man = load_js(os.path.join(AUDIO, "manifest_audio.js"), "PM_AUDIO")
    # 确定 idx 范围
    if ch_str:
        order = int(ch_str) - 1
        sec = next(s for s in data["sections"] if s["order"] == order)
        idx_list = list(range(sec["ruleStart"], sec["ruleEnd"] + 1))
    elif idx_str:
        idx_list = [int(x) for x in idx_str.split(",")]
    else:
        # 全量: 所有有真人clip的句子
        idx_list = [int(k) for k in man["sentences"] if man["sentences"][k].get("clip")]
    upd = []
    for idx in idx_list:
        try:
            rec = man["sentences"].get(str(idx))
            if not rec or not rec.get("clip"):
                continue
            clip_path = os.path.join(APP, rec["clip"])
            if not os.path.exists(clip_path):
                continue
            rule = data["rules"][idx]
            wl = [w.get("p") or w.get("word") for w in rule.get("words", []) if w.get("p")]
            if not wl:
                continue
            res, D = align_clip_words(sess, vocab, clip_path, wl)
            if res is None:
                print("idx%d clip解码失败/太短,跳过" % idx, flush=True); continue
            words = []
            for w, (t0, t1) in zip(wl, res):
                t0 = max(0.0, t0); t1 = min(D, t1)
                if t1 <= t0: t1 = min(D, t0 + 0.06)
                words.append({"p": w, "z": "", "t0": round(t0, 3), "t1": round(t1, 3)})
            if words: words[-1]["t1"] = round(D, 3)
            rec2 = dict(rec); rec2["t1"] = round(D, 3); rec2["words"] = words
            man["sentences"][str(idx)] = rec2
            upd.append(idx)
            if len(upd) % 50 == 0:
                print("  ...已处理 %d" % len(upd), flush=True)
        except Exception as ex:
            print("idx%d异常:%s" % (idx, str(ex)[:80]), flush=True)
            continue
    # 备份+写
    if upd:
        ts = time.strftime("%Y%m%d_%H%M%S")
        os.system('cp "%s" "%s.bak_word_%s" 2>nul' % (os.path.join(AUDIO, "manifest_audio.js"),
                                                       os.path.join(AUDIO, "manifest_audio.js"), ts))
        open(os.path.join(AUDIO, "manifest_audio.js"), "w", encoding="utf-8").write(
            "/* 巴帝摩卡音频 */\nwindow.PM_AUDIO = %s;\n" % json.dumps(man, ensure_ascii=False))
        print("已重建 %d 句 words: %s" % (len(upd), upd))

if __name__ == "__main__":
    main()
